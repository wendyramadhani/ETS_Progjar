import socket
import json
import base64
import logging
import os
import sys
import time # Import modul time untuk delay

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG, # Ubah ke DEBUG untuk log lebih detail
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Alamat server, akan diatur ulang di main
server_address = ('0.0.0.0', 6666) 

# Variabel global untuk socket klien agar bisa diakses oleh fungsi koneksi ulang
client_socket = None

def connect_to_server(server_address, retries=3, delay=2):
    """
    Mencoba menghubungkan ke server dengan jumlah percobaan tertentu.
    Mengembalikan objek socket yang terhubung atau None jika gagal.
    """
    for i in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            logging.debug(f"Percobaan {i+1}/{retries}: Mencoba menghubungkan ke {server_address}")
            sock.connect(server_address)
            logging.warning("Koneksi berhasil dibuat.")
            return sock
        except ConnectionRefusedError:
            logging.error(f"Percobaan {i+1}/{retries}: Koneksi ditolak. Pastikan server berjalan di {server_address}.")
        except socket.timeout:
            logging.error(f"Percobaan {i+1}/{retries}: Timeout saat menghubungkan.")
        except Exception as e:
            logging.error(f"Percobaan {i+1}/{retries}: Terjadi error saat menghubungkan: {e}", exc_info=True)
        
        sock.close() # Pastikan socket ditutup jika gagal
        if i < retries - 1:
            logging.info(f"Menunggu {delay} detik sebelum mencoba lagi...")
            time.sleep(delay)
    logging.critical(f"Gagal terhubung ke server setelah {retries} percobaan.")
    return None

def send_command_persistent(sock, command_dict, timeout=10000):
    """
    Mengirim perintah dalam bentuk dictionary ke server dan menerima respons.
    Menggunakan socket yang sudah ada (persistent connection).
    """
    # Pastikan sock adalah objek socket yang valid
    if sock is None:
        logging.error("Socket tidak valid untuk mengirim perintah.")
        return False

    sock.settimeout(timeout)

    try:
        logging.warning(f"Mengirim perintah: {command_dict.get('command', 'UNKNOWN')}")
        
        command_json_str = json.dumps(command_dict)
        command_bytes = (command_json_str + '\r\n\r\n').encode('utf-8')
        
        logging.debug(f"Mengirim bytes: {command_bytes[:200]}...")
        sock.sendall(command_bytes)
        logging.debug("Data berhasil dikirim.")
        
        data_received = ""
        while True:
            data = sock.recv(4096)
            if data:
                data_received += data.decode('utf-8')
                logging.debug(f"Menerima data: {data_received[:200]}...")
                if "\r\n\r\n" in data_received:
                    logging.debug("Delimiter respons ditemukan.")
                    break
            else:
                logging.warning("Server menutup koneksi atau tidak ada lagi data yang diterima.")
                return False 
        
        if "\r\n\r\n" in data_received:
            json_part, _ = data_received.split("\r\n\r\n", 1)
        else:
            json_part = data_received

        if not json_part:
            logging.error("Tidak ada data JSON yang diterima dari server.")
            return False

        hasil = json.loads(json_part)
        logging.warning("Data diterima dari server.")
        return hasil
    
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON dari server: {e}. Data diterima: '{data_received}'")
        return False
    except socket.timeout:
        logging.error(f"Operasi socket timeout. Periksa jaringan atau status server.")
        return False
    except ConnectionResetError:
        logging.error(f"Koneksi direset oleh peer (server).")
        return False
    except Exception as e:
        logging.error(f"Terjadi error tak terduga dalam send_command_persistent: {e}", exc_info=True)
        return False

# --- Fungsi remote_list, remote_get, remote_upload, remote_delete tetap sama ---
# Mereka akan membuat dictionary perintah yang benar dan memanggil send_command_persistent

def remote_list(sock):
    command_dict = {"command": "LIST", "params": []}
    hasil = send_command_persistent(sock, command_dict)
    if hasil and hasil.get('status') == 'OK':
        print("Daftar file:")
        for nmfile in hasil.get('data', []):
            print(f"- {nmfile}")
        return True
    else:
        print("Gagal LIST:", hasil.get('data', 'Unknown error'))
        return False

def remote_get(sock, filename=""):
    command_dict = {"command": "GET", "params": [filename]}
    hasil = send_command_persistent(sock, command_dict)
    if hasil and hasil.get('status') == 'OK':
        namafile = hasil.get('data_namafile')
        isifile_b64 = hasil.get('data_file')
        if namafile and isifile_b64:
            try:
                isifile = base64.b64decode(isifile_b64)
                with open(namafile, 'wb+') as fp:
                    fp.write(isifile)
                print(f"File '{namafile}' berhasil diunduh.")
                return True
            except Exception as e:
                print(f"Error saat menyimpan file '{namafile}': {e}")
                return False
        else:
            print("Respons GET tidak lengkap (nama file atau data file hilang).")
            return False
    else:
        print("Gagal GET:", hasil.get('data', 'Unknown error'))
        return False

def remote_upload(sock, filename=""):
    if not os.path.exists(filename):
        print(f"File '{filename}' tidak ditemukan.")
        return False

    try:
        with open(filename, "rb") as fp:
            file_content = fp.read()
        encoded_content = base64.b64encode(file_content).decode('utf-8')

        command_dict = {
            'command': 'UPLOAD',
            'params': [filename, encoded_content]
        }
        hasil = send_command_persistent(sock, command_dict)
        # Perubahan ada di sini:
        if hasil is False: # Jika send_command_persistent mengembalikan False
            print("Gagal mengirim perintah UPLOAD ke server.")
            return False
        
        if hasil and hasil.get('status') == 'OK':
            print(f"File '{filename}' berhasil diupload.")
            return True
        else:
            print("Gagal upload:", hasil.get('data', 'Unknown error'))
            return False
    except Exception as e:
        print(f"Error saat upload: {e}")
        return False

def remote_delete(sock, filename=""):
    command_dict = {"command": "DELETE", "params": [filename]}
    hasil = send_command_persistent(sock, command_dict)
    if hasil and hasil.get('status') == 'OK':
        print(hasil.get('data', 'File berhasil dihapus.'))
        return True
    else:
        print("Delete gagal:", hasil.get('data', 'Unknown error'))
        return False

def generate_binary_file(filename, size_in_mb):
    """
    Menggenerate file biner dengan ukuran tertentu (dalam MB).
    File akan diisi dengan byte nol (null bytes).
    """
    try:
        size_in_bytes = size_in_mb * 1024 * 1024
        print(f"Membuat file biner '{filename}' dengan ukuran {size_in_mb} MB ({size_in_bytes} bytes)...")
        with open(filename, 'wb') as f:
            f.seek(size_in_bytes - 1)
            f.write(b'\0')
        print(f"File '{filename}' berhasil dibuat.")
        return True
    except Exception as e:
        print(f"Gagal membuat file biner: {e}")
        return False

if __name__ == '__main__':
    server_address = ('172.16.16.101', 6666)
    generate_binary_file("coba",10)

    # Inisialisasi koneksi awal
    client_socket = connect_to_server(server_address)
    if client_socket is None:
        sys.exit(1) # Keluar jika koneksi awal gagal

    try:
        while True:
            perintah_input = input("Masukkan perintah (LIST, GET <file>, UPLOAD <file>, DELETE <file>, RECONNECT, EXIT): ").strip()

            if perintah_input.upper() == "EXIT":
                print("Keluar dari program.")
                break
            elif perintah_input.upper() == "RECONNECT":
                if client_socket:
                    logging.warning("Menutup koneksi lama untuk sambung ulang...")
                    client_socket.close()
                client_socket = connect_to_server(server_address)
                if client_socket is None:
                    print("Gagal menyambung ulang. Coba RECONNECT lagi atau EXIT.")
                    # Jika gagal sambung ulang, mungkin ingin melanjutkan loop atau keluar
                    continue 
                else:
                    print("Berhasil menyambung ulang.")
                    continue # Lanjutkan ke loop berikutnya untuk perintah baru
            
            # Jika socket tidak aktif, minta pengguna untuk menyambung ulang
            if client_socket is None:
                print("Koneksi tidak aktif. Silakan ketik 'RECONNECT' untuk mencoba menyambung kembali.")
                continue

            elif perintah_input.upper() == "LIST":
                remote_list(client_socket)

            elif perintah_input.upper().startswith("GET "):
                try:
                    filename = perintah_input.split(" ", 1)[1].strip('"')
                    remote_get(client_socket, filename)
                except IndexError:
                    print("Format salah. Contoh: GET \"file.jpg\"")

            elif perintah_input.upper().startswith("UPLOAD "):
                try:
                    filename = perintah_input.split(" ", 1)[1].strip('"')
                    remote_upload(client_socket, filename)
                except IndexError:
                    print("Format salah. Contoh: UPLOAD \"file.jpg\"")

            elif perintah_input.upper().startswith("DELETE "):
                try:
                    filename = perintah_input.split(" ", 1)[1].strip('"')
                    remote_delete(client_socket, filename)
                except IndexError:
                    print("Format salah. Contoh: DELETE \"file.jpg\"")

            else:
                print("Perintah tidak dikenali.")
    except KeyboardInterrupt:
        print("Klien dihentikan secara manual.")
    except Exception as e:
        print(f"Terjadi error fatal di loop utama: {e}")
        sys.exit(1)
    finally:
        if client_socket:
            client_socket.close()
            logging.warning("Koneksi klien ditutup.")
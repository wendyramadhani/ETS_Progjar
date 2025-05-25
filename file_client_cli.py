import socket
import json
import base64
import logging
import os
import sys
import time # Import modul time untuk delay

# Konfigurasi logging
logging.basicConfig(level=logging.WARNING, # Ubah ke WARNING agar tidak terlalu banyak log saat stress test
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Alamat server, akan diatur ulang di main
server_address = ('0.0.0.0', 6666)

# Variabel global untuk socket klien agar bisa diakses oleh fungsi koneksi ulang
client_socket = None

def connect_to_server(server_address, retries=1, delay=0.1): # Kurangi retries dan delay untuk stress test
    """
    Mencoba menghubungkan ke server dengan jumlah percobaan tertentu.
    Mengembalikan objek socket yang terhubung atau None jika gagal.
    """
    for i in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(server_address)
            return sock
        except ConnectionRefusedError:
            logging.error(f"Percobaan {i+1}/{retries}: Koneksi ditolak. Pastikan server berjalan di {server_address}.")
        except socket.timeout:
            logging.error(f"Percobaan {i+1}/{retries}: Timeout saat menghubungkan.")
        except Exception as e:
            logging.error(f"Percobaan {i+1}/{retries}: Terjadi error saat menghubungkan: {e}", exc_info=True)

        sock.close() # Pastikan socket ditutup jika gagal
        if i < retries - 1:
            time.sleep(delay)
    logging.critical(f"Gagal terhubung ke server setelah {retries} percobaan.")
    return None

def send_command_persistent(sock, command_dict, timeout=60, client_id=None): # Tambahkan client_id
    """
    Mengirim perintah dalam bentuk dictionary ke server dan menerima respons.
    Menggunakan socket yang sudah ada (persistent connection).
    """
    client_prefix = f"(Client {client_id}) " if client_id is not None else ""

    if sock is None:
        logging.error(f"{client_prefix}Socket tidak valid untuk mengirim perintah.")
        return False

    sock.settimeout(timeout)

    try:
        command_json_str = json.dumps(command_dict)
        command_bytes = (command_json_str + '\r\n\r\n').encode('utf-8')

        logging.debug(f"{client_prefix}Mengirim perintah: {command_dict.get('command', 'UNKNOWN')}")
        sock.sendall(command_bytes)
        logging.debug(f"{client_prefix}Data berhasil dikirim.")

        data_received = ""
        while True:
            data = sock.recv(1024*1024) # Gunakan buffer lebih besar untuk performa
            if data:
                data_received += data.decode('utf-8')
                if "\r\n\r\n" in data_received:
                    break
            else:
                logging.warning(f"{client_prefix}Server menutup koneksi atau tidak ada lagi data yang diterima.")
                return False

        if "\r\n\r\n" in data_received:
            json_part, _ = data_received.split("\r\n\r\n", 1)
        else:
            json_part = data_received

        if not json_part:
            logging.error(f"{client_prefix}Tidak ada data JSON yang diterima dari server.")
            return False

        hasil = json.loads(json_part)
        logging.debug(f"{client_prefix}Data diterima dari server.")
        return hasil

    except json.JSONDecodeError as e:
        logging.error(f"{client_prefix}Error decoding JSON dari server: {e}. Data diterima: '{data_received}'")
        return False
    except socket.timeout:
        logging.error(f"{client_prefix}Operasi socket timeout. Periksa jaringan atau status server.")
        return False
    except ConnectionResetError:
        logging.error(f"{client_prefix}Koneksi direset oleh peer (server).")
        return False
    except Exception as e:
        logging.error(f"{client_prefix}Terjadi error tak terduga dalam send_command_persistent: {e}", exc_info=True)
        return False

def remote_list(sock, client_id=None): # Tambahkan client_id
    client_prefix = f"(Client {client_id}) " if client_id is not None else ""
    command_dict = {"command": "LIST", "params": []}
    hasil = send_command_persistent(sock, command_dict, client_id=client_id)
    if hasil and hasil.get('status') == 'OK':
        logging.debug(f"{client_prefix}LIST berhasil.")
        return True
    else:
        logging.error(f"{client_prefix}Gagal LIST: {hasil.get('data', 'Unknown error')}")
        return False

def remote_get(sock, filename="", client_id=None): # Tambahkan client_id
    client_prefix = f"(Client {client_id}) " if client_id is not None else ""
    command_dict = {"command": "GET", "params": [filename]}
    hasil = send_command_persistent(sock, command_dict, client_id=client_id)

    # --- THE CRITICAL FIX IS HERE ---
    # Check if 'hasil' is explicitly False (indicating an error from send_command_persistent)
    if hasil is False:
        logging.error(f"{client_prefix}Gagal menerima respons GET dari server (send_command_persistent failed).")
        return False
    # --- END OF CRITICAL FIX ---

    if hasil and hasil.get('status') == 'OK':
        namafile = hasil.get('data_namafile')
        isifile_b64 = hasil.get('data_file')
        if namafile and isifile_b64:
            try:
                isifile = base64.b64decode(isifile_b64)
                # Untuk stress testing, umumnya kita tidak menyimpan file yang diunduh
                # untuk menghindari bottleneck I/O di sisi klien, kecuali jika verifikasi diperlukan.
                logging.debug(f"{client_prefix}GET file '{namafile}' berhasil.")
                return True
            except Exception as e:
                logging.error(f"{client_prefix}Error decoding atau menangani file yang diunduh '{namafile}': {e}")
                return False
        else:
            logging.error(f"{client_prefix}Respons GET tidak lengkap (nama file atau data file hilang).")
            return False
    else:
        # This else block is reached if 'hasil' is not False, but either:
        # 1. 'hasil' is None (less likely if send_command_persistent always returns dict or False)
        # 2. 'hasil' is a dictionary, but 'status' is not 'OK'
        logging.error(f"{client_prefix}Gagal GET: {hasil.get('data', 'Unknown error')}. Status: {hasil.get('status', 'N/A')}")
        return False

def remote_upload(sock, filename="", client_id=None): # Tambahkan client_id
    client_prefix = f"(Client {client_id}) " if client_id is not None else ""
    
    print(f"{client_prefix}DEBUG (remote_upload di client.py): Memeriksa keberadaan file lokal: {filename}")
    if not os.path.exists(filename):
        print(f"{client_prefix}ERROR (remote_upload di client.py): File '{filename}' tidak ditemukan secara lokal.")
        return False

    try:
        with open(filename, "rb") as fp:
            file_content = fp.read()
        encoded_content = base64.b64encode(file_content).decode('utf-8')

        command_dict = {
            'command': 'UPLOAD',
            'params': [os.path.basename(filename), encoded_content] # Kirim hanya basename ke server
        }
        print(f"{client_prefix}DEBUG (remote_upload di client.py): Mengirim perintah UPLOAD untuk basename: {os.path.basename(filename)}")
        hasil = send_command_persistent(sock, command_dict, client_id=client_id)

        if hasil is False:
            logging.error(f"{client_prefix}Gagal mengirim perintah UPLOAD ke server.")
            return False

        if hasil and hasil.get('status') == 'OK':
            logging.debug(f"{client_prefix}UPLOAD file '{os.path.basename(filename)}' berhasil.")
            return True
        else:
            logging.error(f"{client_prefix}Gagal upload: {hasil.get('data', 'Unknown error')}")
            return False
    except Exception as e:
        logging.error(f"{client_prefix}Error saat upload di remote_upload: {e}", exc_info=True)
        return False

def remote_delete(sock, filename="", client_id=None): # Tambahkan client_id
    client_prefix = f"(Client {client_id}) " if client_id is not None else ""
    command_dict = {"command": "DELETE", "params": [filename]}
    hasil = send_command_persistent(sock, command_dict, client_id=client_id)
    if hasil and hasil.get('status') == 'OK':
        logging.debug(f"{client_prefix}DELETE file '{filename}' berhasil.")
        return True
    else:
        logging.error(f"{client_prefix}Delete gagal: {hasil.get('data', 'Unknown error')}")
        return False

def generate_binary_file(filename, size_in_mb):
    """
    Menggenerate file biner dengan ukuran tertentu (dalam MB).
    File akan diisi dengan byte nol (null bytes).
    filename: Jalur lengkap di mana file harus dibuat.
    """
    try:
        size_in_bytes = size_in_mb * 1024 * 1024
        print(f"DEBUG (generate_binary_file): Membuat file '{filename}' dengan ukuran {size_in_mb} MB.")
        with open(filename, 'wb') as f:
            f.seek(size_in_bytes - 1)
            f.write(b'\0')
        print(f"DEBUG (generate_binary_file): File '{filename}' berhasil dibuat.")
        return True
    except Exception as e:
        logging.error(f"Gagal membuat file biner: {e}")
        return False

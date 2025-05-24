from socket import *
import socket
import threading
import logging
import time
import sys
from concurrent.futures import ThreadPoolExecutor # Import ThreadPoolExecutor

# Asumsi file_protocol.py ada dan berisi kelas FileProtocol
# yang memiliki metode proses_string(message)
from file_protocol import FileProtocol
fp = FileProtocol()

# Konfigurasi logging
logging.basicConfig(level=logging.WARNING,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ClientHandler:
    """
    Kelas ini menangani komunikasi dengan satu klien.
    Tidak lagi mewarisi dari threading.Thread karena akan dijalankan oleh ThreadPoolExecutor.
    """
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        logging.info(f"Client handler created for {address}")

    def run(self):
        """
        Metode ini berisi logika untuk memproses data dari klien.
        """
        buffer = ""
        try:
            logging.warning(f"Starting to process client {self.address}")
            while True:
                # Menerima data dari klien
                data = self.connection.recv(4096)
                if not data:
                    logging.warning(f"Client {self.address} disconnected gracefully.")
                    break # Klien terputus

                buffer += data.decode('utf-8') # Decode data yang diterima

                # Memproses pesan jika ada pemisah "\r\n\r\n"
                while "\r\n\r\n" in buffer:
                    message, buffer = buffer.split("\r\n\r\n", 1)
                    logging.info(f"Received message from {self.address}: {message[:50]}...") # Log 50 karakter pertama
                    
                    # Memproses pesan menggunakan FileProtocol
                    hasil = fp.proses_string(message)
                    hasil += "\r\n\r\n" # Tambahkan pemisah kembali untuk respons

                    # Mengirim hasil kembali ke klien
                    self.connection.sendall(hasil.encode('utf-8'))
                    logging.info(f"Sent response to {self.address}: {hasil[:50]}...") # Log 50 karakter pertama
        except ConnectionResetError:
            logging.warning(f"Client {self.address} forcibly disconnected.")
        except Exception as e:
            logging.error(f"Error processing client {self.address}: {e}", exc_info=True)
        finally:
            logging.warning(f"Closing connection for {self.address}")
            self.connection.close()

class Server(threading.Thread):
    """
    Kelas Server menerima koneksi klien dan menyerahkannya ke thread pool.
    """
    def __init__(self, ipaddress='0.0.0.0', port=8889, max_workers=10):
        self.ipinfo = (ipaddress, port)
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.executor = ThreadPoolExecutor(max_workers=max_workers) # Inisialisasi thread pool
        threading.Thread.__init__(self)
        self.daemon = True # Menjadikan thread daemon agar program bisa keluar jika main thread selesai

    def run(self):
        """
        Metode run server yang menerima koneksi.
        """
        logging.warning(f"Server berjalan di IP address {self.ipinfo[0]} port {self.ipinfo[1]}")
        try:
            self.my_socket.bind(self.ipinfo)
            self.my_socket.listen(5) # Maksimal 5 koneksi yang tertunda
        except Exception as e:
            logging.critical(f"Failed to start server: {e}")
            sys.exit(1) # Keluar jika server tidak bisa dimulai

        while True:
            try:
                connection, client_address = self.my_socket.accept()
                logging.warning(f"Koneksi dari {client_address}")
                
                # Membuat instance ClientHandler dan menyerahkan metode run-nya ke thread pool
                handler = ClientHandler(connection, client_address)
                self.executor.submit(handler.run) # Menyerahkan tugas ke thread pool
            except KeyboardInterrupt:
                logging.warning("Server dimatikan oleh pengguna.")
                break
            except Exception as e:
                logging.error(f"Error accepting new connection: {e}", exc_info=True)
        
        # Menutup thread pool saat server berhenti
        self.executor.shutdown(wait=True)
        self.my_socket.close()
        logging.warning("Server berhenti.")


def main():
    """
    Fungsi utama untuk menjalankan server.
    """
    # Anda bisa mengatur port di sini
    svr = Server(ipaddress='0.0.0.0', port=6666, max_workers=20) # Contoh dengan 20 worker thread
    svr.start()
    
    # Menjaga main thread tetap hidup agar server daemon thread bisa berjalan
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.warning("Main thread dimatikan.")
        sys.exit(0)


if __name__ == "__main__":
    main()

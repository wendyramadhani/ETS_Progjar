from socket import *
import socket
import threading
import logging
import time
import sys
from concurrent.futures import ThreadPoolExecutor # Or ProcessPoolExecutor

# Asumsi file_protocol.py ada dan berisi kelas FileProtocol
# yang memiliki metode proses_string(message)
from file_protocol import FileProtocol

# Konfigurasi logging
logging.basicConfig(level=logging.WARNING,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ClientHandler:
    """
    Kelas ini menangani komunikasi dengan satu klien.
    """
    def __init__(self, connection, address, server_stats): # Tambahkan server_stats sebagai argumen
        self.connection = connection
        self.address = address
        self.fp = FileProtocol() # Setiap handler memiliki instance FileProtocol-nya sendiri
        self.server_stats = server_stats # Referensi ke objek statistik server
        logging.info(f"Client handler created for {address}")

    def run(self):
        """
        Metode ini berisi logika untuk memproses data dari klien.
        """
        buffer = ""
        try:
            logging.warning(f"Starting to process client {self.address}")
            while True:
                data = self.connection.recv(4096)
                if not data:
                    logging.warning(f"Client {self.address} disconnected gracefully.")
                    break

                buffer += data.decode('utf-8')

                while "\r\n\r\n" in buffer:
                    message, buffer = buffer.split("\r\n\r\n", 1)
                    logging.info(f"Received message from {self.address}: {message[:50]}...")
                    
                    # === START: Handle GET_SERVER_STATS command ===
                    if message.strip() == "GET_SERVER_STATS":
                        with self.server_stats['lock']:
                            stats_response = (
                                f"SERVER_STATS_SUCCESS:{self.server_stats['successful_operations']}"
                                f"\r\nSERVER_STATS_FAILED:{self.server_stats['failed_operations']}"
                            )
                        stats_response += "\r\n\r\n" # Always end with separator
                        self.connection.sendall(stats_response.encode('utf-8'))
                        logging.info(f"Sent server stats to {self.address}")
                        # After sending stats, gracefully close this connection
                        return # Exit run method for this special request
                    # === END: Handle GET_SERVER_STATS command ===

                    # Original file protocol processing
                    hasil = self.fp.proses_string(message)
                    hasil += "\r\n\r\n"

                    self.connection.sendall(hasil.encode('utf-8'))
                    logging.info(f"Sent response to {self.address}: {hasil[:50]}...")
                    
                    # Update successful operations count only for actual file operations
                    with self.server_stats['lock']:
                        self.server_stats['successful_operations'] += 1

        except ConnectionResetError:
            logging.warning(f"Client {self.address} forcibly disconnected.")
            with self.server_stats['lock']:
                self.server_stats['failed_operations'] += 1
        except Exception as e:
            logging.error(f"Error processing client {self.address}: {e}", exc_info=True)
            with self.server_stats['lock']:
                self.server_stats['failed_operations'] += 1
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
        self.executor = ThreadPoolExecutor(max_workers=max_workers) # Using ThreadPoolExecutor
        threading.Thread.__init__(self)
        self.daemon = True
        
        self.server_stats = {
            'successful_operations': 0,
            'failed_operations': 0,
            'lock': threading.Lock() # Lock untuk mengamankan akses ke penghitung
        }

    def run(self):
        """
        Metode run server yang menerima koneksi.
        """
        logging.warning(f"Server berjalan di IP address {self.ipinfo[0]} port {self.ipinfo[1]}")
        try:
            self.my_socket.bind(self.ipinfo)
            self.my_socket.listen(5)
        except Exception as e:
            logging.critical(f"Failed to start server: {e}")
            sys.exit(1)

        while True:
            try:
                connection, client_address = self.my_socket.accept()
                logging.warning(f"Koneksi dari {client_address}")
                
                handler = ClientHandler(connection, client_address, self.server_stats)
                self.executor.submit(handler.run)
            except KeyboardInterrupt:
                logging.warning("Server dimatikan oleh pengguna.")
                break
            except Exception as e:
                logging.error(f"Error accepting new connection: {e}", exc_info=True)
        
        self.executor.shutdown(wait=True)
        self.my_socket.close()
        
        logging.warning("========================================")
        logging.warning("STATISTIK OPERASI SERVER AKHIR:")
        with self.server_stats['lock']:
            logging.warning(f"  Total Operasi Sukses: {self.server_stats['successful_operations']}")
            logging.warning(f"  Total Operasi Gagal: {self.server_stats['failed_operations']}")
        logging.warning("========================================")
        logging.warning("Server berhenti.")


def main():
    """
    Fungsi utama untuk menjalankan server.
    """
    svr = Server(ipaddress='0.0.0.0', port=6666, max_workers=50)
    svr.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.warning("Main thread dimatikan.")
        sys.exit(0)


if __name__ == "__main__":
    main()
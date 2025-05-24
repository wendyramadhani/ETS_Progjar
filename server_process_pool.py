from socket import *
import socket
import logging
import time
import sys
import os
from concurrent.futures import ProcessPoolExecutor

# Asumsi file_protocol.py ada dan berisi kelas FileProtocol
from file_protocol import FileProtocol

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - [PID:%(process)d] - %(message)s')

class ClientHandler:
    """
    Kelas ini menangani komunikasi dengan satu klien.
    Akan dijalankan oleh ProcessPoolExecutor di dalam proses worker terpisah.
    """
    def __init__(self):
        logging.debug(f"ClientHandler __init__ called in process {os.getpid()}")
        try:
            self.fp = FileProtocol()
            logging.debug(f"FileProtocol instance created successfully in process {os.getpid()}")
        except Exception as e:
            logging.critical(f"ERROR: Failed to create FileProtocol instance in process {os.getpid()}: {e}", exc_info=True)
            raise

    def run(self, conn_fileno, address): # Menerima fileno, bukan connection object
        """
        Metode ini berisi logika untuk memproses data dari klien.
        Menerima file descriptor koneksi dan alamat klien.
        """
        # Rekonstruksi socket dari file descriptor di dalam proses worker
        connection = socket.fromfd(conn_fileno, socket.AF_INET, socket.SOCK_STREAM)
        connection.setblocking(True) # Pastikan socket berada dalam mode blocking
        # Penting: Tutup fileno asli karena socket.fromfd membuat duplikat
        # Namun, untuk soket yang diterima dari accept(), fileno-nya sudah valid
        # dan akan ditutup saat connection.close() dipanggil.

        logging.warning(f"Starting to process client {address} in process {os.getpid()}")
        buffer = ""
        try:
            while True:
                data = connection.recv(4096)
                if not data:
                    logging.warning(f"Client {address} disconnected gracefully (PID:{os.getpid()}).")
                    break

                buffer += data.decode('utf-8')

                while "\r\n\r\n" in buffer:
                    message, buffer = buffer.split("\r\n\r\n", 1)
                    logging.info(f"Received message from {address} (PID:{os.getpid()}): {message[:100]}...")
                     
                    hasil = self.fp.proses_string(message)
                    hasil += "\r\n\r\n"

                    connection.sendall(hasil.encode('utf-8'))
                    logging.info(f"Sent response to {address} (PID:{os.getpid()}): {hasil[:100]}...")
        except ConnectionResetError:
            logging.warning(f"Client {address} forcibly disconnected (PID:{os.getpid()}).")
        except Exception as e:
            logging.error(f"Error processing client {address} (PID:{os.getpid()}): {e}", exc_info=True)
        finally:
            logging.warning(f"Closing connection for {address} (PID:{os.getpid()})")
            connection.close()

def main():
    ipaddress = '0.0.0.0'
    port = 6666
    max_workers = os.cpu_count() if os.cpu_count() else 4 

    logging.warning(f"Server berjalan di IP address {ipaddress} port {port} (Main PID:{os.getpid()})")
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((ipaddress, port))
        server_socket.listen(5)
    except Exception as e:
        logging.critical(f"Gagal memulai server: {e} (Main PID:{os.getpid()})")
        sys.exit(1)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        logging.warning(f"Process Pool Executor dengan {max_workers} worker dimulai (Main PID:{os.getpid()}).")
        try:
            while True:
                connection, client_address = server_socket.accept()
                logging.warning(f"Koneksi baru diterima dari {client_address} (Main PID:{os.getpid()})")
                 
                # Pass the file descriptor to the worker
                executor.submit(ClientHandler().run, connection.fileno(), client_address)
                 
                # Crucially, close the connection in the main process IMMEDIATELY
                # after submitting its file descriptor to the worker.
                # This transfers ownership of the socket to the worker process.
                connection.close()

        except KeyboardInterrupt:
            logging.warning("Server dimatikan oleh pengguna (Main PID:{os.getpid()}).")
        except Exception as e:
            logging.error(f"Error saat menerima koneksi baru (Main PID:{os.getpid()}): {e}", exc_info=True)
        finally:
            logging.warning("Menunggu semua tugas di Process Pool Executor selesai...")
            # This 'pass' can be removed if you don't need any specific cleanup here
            pass

    server_socket.close()
    logging.warning("Server berhenti (Main PID:{os.getpid()}).")

if __name__ == "__main__":
    main()
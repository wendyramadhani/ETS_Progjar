import os
import time
import concurrent.futures
import threading
import math
from datetime import datetime
import csv
import socket # Import socket for the new stats request

# Import fungsi-fungsi dari client.py yang sudah dimodifikasi
from file_client_cli import connect_to_server, remote_upload, remote_get, generate_binary_file, remote_delete

# --- START: Pengaturan Jalur Absolut ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.join(BASE_DIR, "test_files")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloaded_files")
RESULTS_DIR = os.path.join(BASE_DIR, "test_results")

os.makedirs(TEST_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

print(f"DEBUG: BASE_DIR: {BASE_DIR}")
print(f"DEBUG: TEST_DIR (untuk file yang dihasilkan): {TEST_DIR}")
print(f"DEBUG: DOWNLOAD_DIR (untuk file yang diunduh): {DOWNLOAD_DIR}")
print(f"DEBUG: RESULTS_DIR (untuk hasil CSV): {RESULTS_DIR}")
# --- END: Pengaturan Jalur Absolut ---


# Konfigurasi pengujian
SERVER_IP = '172.16.16.101' # Ganti dengan IP server Anda
SERVER_PORT = 6666

OPERATIONS = ['upload', 'get']
FILE_VOLUMES_MB = [10, 50, 100]
CLIENT_WORKER_POOLS = [1, 5, 50]
SERVER_WORKER_POOLS = [1, 5, 50] # This is now just for reporting what server config was expected

# Hasil pengujian
results = []
lock = threading.Lock() # Untuk mengamankan akses ke daftar hasil

def run_client_task(client_id, op_type, local_file_full_path, file_size_bytes, server_address_tuple):
    """
    Fungsi yang dijalankan oleh setiap worker client.
    Melakukan operasi upload atau get (download) dan mengukur waktunya.
    """
    client_conn_success = False
    client_op_success = False
    start_time = time.time()
    
    print(f"DEBUG (Client {client_id}): Memulai {op_type} untuk {os.path.basename(local_file_full_path)}...")
    
    sock = connect_to_server(server_address_tuple)
    if sock:
        client_conn_success = True
        try:
            if op_type == 'upload':
                client_op_success = remote_upload(sock, local_file_full_path, client_id=client_id)
            elif op_type == 'get':
                server_filename_for_request = os.path.basename(local_file_full_path)
                client_op_success = remote_get(sock, server_filename_for_request, client_id=client_id)
        except Exception as e:
            print(f"ERROR (Client {client_id}): Exception selama operasi {op_type}: {e}")
            client_op_success = False
        finally:
            if sock:
                sock.close()
                print(f"DEBUG (Client {client_id}): Koneksi ditutup.")
    else:
        print(f"ERROR (Client {client_id}): Gagal terhubung ke server.")
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"DEBUG (Client {client_id}): {op_type} {os.path.basename(local_file_full_path)} {'berhasil' if client_op_success else 'gagal'} dalam {total_time:.2f} detik.")

    return {
        'worker_id': client_id,
        'total_time': total_time,
        'success': client_op_success,
        'conn_success': client_conn_success,
        'bytes_processed': file_size_bytes if client_op_success else 0
    }

def run_test_combination(operation, file_volume_mb, client_workers, server_workers_info):
    """
    Menjalankan satu kombinasi pengujian.
    """
    print(f"\n--- Memulai Uji Kombinasi ---")
    print(f"Operasi: {operation.upper()}, Volume File: {file_volume_mb} MB, Klien Worker: {client_workers}, Server Worker (Info): {server_workers_info}")

    file_size_bytes = file_volume_mb * 1024 * 1024
    
    test_file_name_full_path = os.path.join(TEST_DIR, f"test_file_{file_volume_mb}MB.bin")
    downloaded_file_path = os.path.join(DOWNLOAD_DIR, os.path.basename(test_file_name_full_path))

    if operation == 'upload':
        print(f"DEBUG (run_test_combination): Membuat file di: {test_file_name_full_path}")
        if not generate_binary_file(test_file_name_full_path, file_volume_mb):
            print(f"Gagal membuat file dummy: {test_file_name_full_path}. Melewati kombinasi ini.")
            return
    elif operation == 'get':
        if not os.path.exists(test_file_name_full_path):
            print(f"Peringatan: File {os.path.basename(test_file_name_full_path)} tidak ada secara lokal untuk operasi GET. Pastikan file ini ada di server.")
        pass

    server_address_tuple = (SERVER_IP, SERVER_PORT)
    
    individual_client_results = []
    
    successful_clients = 0
    failed_clients = 0
    total_time_per_client_sum = 0
    total_bytes_processed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=client_workers) as executor:
        futures = []
        for i in range(client_workers):
            futures.append(executor.submit(run_client_task, i + 1, operation, test_file_name_full_path, file_size_bytes, server_address_tuple))

        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                individual_client_results.append(result)
                if result['success']:
                    successful_clients += 1
                    total_time_per_client_sum += result['total_time']
                    total_bytes_processed += result['bytes_processed']
                else:
                    failed_clients += 1
            except Exception as e:
                print(f"ERROR (run_test_combination): Error dalam worker client: {e}")
                failed_clients += 1

    avg_time_per_client = total_time_per_client_sum / successful_clients if successful_clients > 0 else 0
    throughput_per_client = (total_bytes_processed / successful_clients) / avg_time_per_client if successful_clients > 0 and avg_time_per_client > 0 else 0

    # These will still be N/A here, but will be updated later
    server_success_count = 'N/A'
    server_failure_count = 'N/A'

    with lock:
        results.append({
            'operation': operation,
            'file_volume_mb': file_volume_mb,
            'client_workers': client_workers,
            'server_workers_info': server_workers_info,
            'avg_time_per_client_s': avg_time_per_client,
            'throughput_per_client_bps': throughput_per_client,
            'successful_client_workers': successful_clients,
            'failed_client_workers': failed_clients,
            'server_worker_success': server_success_count, # Initial placeholder
            'server_worker_failure': server_failure_count, # Initial placeholder
            'total_bytes_attempted_by_clients': client_workers * file_size_bytes,
            'total_bytes_successfully_processed_by_clients': total_bytes_processed,
            'individual_client_results': individual_client_results
        })
    
    print(f"--- Hasil Kombinasi {operation.upper()} {file_volume_mb}MB, Klien Worker: {client_workers} ---")
    print(f"  Waktu rata-rata per klien sukses: {avg_time_per_client:.4f} detik")
    print(f"  Throughput rata-rata per klien sukses: {throughput_per_client:.2f} bytes/detik")
    print(f"  Klien sukses: {successful_clients}, Klien gagal: {failed_clients}")
    print(f"---------------------------------------------------")

    if operation == 'upload' and os.path.exists(test_file_name_full_path):
        print(f"DEBUG (run_test_combination): Menghapus file yang dihasilkan: {test_file_name_full_path}")
        try:
            os.remove(test_file_name_full_path)
        except OSError as e:
            print(f"ERROR: Gagal menghapus file {test_file_name_full_path}: {e}")
    
    if operation == 'get' and os.path.exists(downloaded_file_path):
        print(f"DEBUG (run_test_combination): Menghapus file yang diunduh: {downloaded_file_path}")
        try:
            os.remove(downloaded_file_path)
        except OSError as e:
            print(f"ERROR: Gagal menghapus file {downloaded_file_path}: {e}")

# --- New function to get server stats ---
def get_server_total_stats(server_address_tuple):
    """
    Connects to the server and requests global success/failure stats.
    Returns (successful_ops, failed_ops) or (None, None) on failure.
    """
    print("\n--- Meminta statistik global dari server ---")
    sock = None
    try:
        sock = connect_to_server(server_address_tuple)
        if not sock:
            print("ERROR: Gagal terhubung ke server untuk mendapatkan statistik.")
            return None, None

        # Send the GET_SERVER_STATS command
        command = "GET_SERVER_STATS\r\n\r\n"
        sock.sendall(command.encode('utf-8'))
        print("DEBUG: Mengirim perintah GET_SERVER_STATS...")

        # Receive response
        buffer = ""
        start_time = time.time()
        while "\r\n\r\n" not in buffer:
            data = sock.recv(4096)
            if not data:
                print("ERROR: Koneksi terputus saat menunggu statistik server.")
                return None, None
            buffer += data.decode('utf-8')
            if time.time() - start_time > 10: # Timeout after 10 seconds
                print("ERROR: Timeout menunggu statistik server.")
                return None, None

        message, _ = buffer.split("\r\n\r\n", 1)
        print(f"DEBUG: Menerima respons statistik: {message}")

        success_count = None
        failed_count = None

        # Parse the response
        lines = message.split('\r\n')
        for line in lines:
            if line.startswith("SERVER_STATS_SUCCESS:"):
                try:
                    success_count = int(line.split(':')[1])
                except ValueError:
                    pass
            elif line.startswith("SERVER_STATS_FAILED:"):
                try:
                    failed_count = int(line.split(':')[1])
                except ValueError:
                    pass

        if success_count is not None and failed_count is not None:
            print(f"Server Stats: Sukses={success_count}, Gagal={failed_count}")
            return success_count, failed_count
        else:
            print("ERROR: Format respons statistik tidak valid.")
            return None, None

    except socket.error as se:
        print(f"ERROR: Socket error saat meminta statistik server: {se}")
        return None, None
    except Exception as e:
        print(f"ERROR: Exception saat meminta statistik server: {e}")
        return None, None
    finally:
        if sock:
            sock.close()
            print("DEBUG: Koneksi statistik ditutup.")

# --- End new function ---

def main():
    for volume in FILE_VOLUMES_MB:
        for client_pool in CLIENT_WORKER_POOLS:
            for server_pool_info in SERVER_WORKER_POOLS: # This is now just for reporting what server config was expected
                run_test_combination('upload', volume, client_pool, server_pool_info)
                run_test_combination('get', volume, client_pool, server_pool_info)
    
    # --- START: Get global server stats and update results ---
    server_address_tuple = (SERVER_IP, SERVER_PORT)
    total_server_success_ops, total_server_failed_ops = get_server_total_stats(server_address_tuple)

    if total_server_success_ops is not None and total_server_failed_ops is not None:
        with lock: # Acquire lock before modifying global results list
            for res in results:
                res['server_worker_success'] = total_server_success_ops
                res['server_worker_failure'] = total_server_failed_ops
        print("INFO: Statistik server global berhasil diambil dan diterapkan ke hasil.")
    else:
        print("WARNING: Gagal mendapatkan statistik server global. Kolom server akan tetap 'N/A'.")
    # --- END: Get global server stats and update results ---

    sorted_results = sorted(results, key=lambda x: (x['client_workers'], x['file_volume_mb'], x['operation']))

    print("\n\n=============== RINGKASAN HASIL PENGUJIAN ===============\n")
    for res in sorted_results:
        print(f"--- Pengujian Dimulai dengan {res['client_workers']} Klien Worker dan File {res['file_volume_mb']} MB ---")
        print(f"Operasi: {res['operation'].upper()}")
        print(f"  Volume File: {res['file_volume_mb']} MB")
        print(f"  Klien Worker: {res['client_workers']}")
        print(f"  Server Worker (Info): {res['server_workers_info']}")
        print(f"  Waktu total per klien (rata-rata sukses): {res['avg_time_per_client_s']:.4f} detik")
        print(f"  Throughput per klien (rata-rata sukses): {res['throughput_per_client_bps']:.2f} bytes/detik")
        print(f"  Klien sukses: {res['successful_client_workers']}, Klien gagal: {res['failed_client_workers']}")
        print(f"  Server sukses: {res['server_worker_success']}, Server gagal: {res['server_worker_failure']}") # Now displays actual numbers
        
        sorted_individual_results = sorted(res['individual_client_results'], key=lambda x: x['worker_id'])
        print("  Detail Kinerja Tiap Worker Klien:")
        for individual_res in sorted_individual_results:
            status = "SUKSES" if individual_res['success'] else "GAGAL"
            print(f"    Worker ID: {individual_res['worker_id']}, Waktu: {individual_res['total_time']:.4f} detik, Status: {status}")
        print("-" * 50)
    
    print("\nDetail hasil tersimpan dalam variabel 'results'. Anda bisa mengolahnya lebih lanjut (misalnya ke CSV/Excel).")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"performance_test_results_{timestamp}.csv"
    save_results_to_csv(sorted_results, csv_filename)


def save_results_to_csv(results_data, filename="performance_test_results.csv"):
    """
    Menyimpan hasil pengujian ke dalam file CSV.
    """
    filepath = os.path.join(RESULTS_DIR, filename)
    with open(filepath, 'w', newline='') as csvfile:
        fieldnames = [
            'Nomor', 'Operasi', 'Volume_MB', 'Jumlah_Client_Worker', 'Jumlah_Server_Worker',
            'Waktu_Total_Per_Client_S', 'Throughput_Per_Client_Bps',
            'Client_Sukses', 'Client_Gagal', 'Server_Sukses', 'Server_Gagal'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for i, res in enumerate(results_data):
            writer.writerow({
                'Nomor': i + 1,
                'Operasi': res['operation'],
                'Volume_MB': res['file_volume_mb'],
                'Jumlah_Client_Worker': res['client_workers'],
                'Jumlah_Server_Worker': res['server_workers_info'],
                'Waktu_Total_Per_Client_S': f"{res['avg_time_per_client_s']:.4f}",
                'Throughput_Per_Client_Bps': f"{res['throughput_per_client_bps']:.2f}",
                'Client_Sukses': res['successful_client_workers'],
                'Client_Gagal': res['failed_client_workers'],
                'Server_Sukses': res['server_worker_success'], # Now will be actual number
                'Server_Gagal': res['server_worker_failure'] # Now will be actual number
            })
    print(f"\nHasil pengujian telah disimpan ke: {filepath}")


if __name__ == '__main__':
    main()
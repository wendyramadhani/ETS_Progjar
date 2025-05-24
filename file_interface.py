import os
import json
import base64
from glob import glob
import logging # Tambahkan logging untuk membantu debugging

class FileInterface:
    def __init__(self):
        # --- INI ADALAH PERUBAHAN STRUKTURAL YANG PENTING ---
        # Dapatkan direktori tempat skrip file_interface.py ini dijalankan.
        # Ini memberikan titik referensi yang stabil untuk jalur file,
        # terlepas dari CWD proses worker.
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Buat jalur lengkap ke folder 'files' di dalam direktori skrip.
        # Ini akan menjadi lokasi penyimpanan file yang konsisten.
        self.storage_dir = os.path.join(self.base_dir, 'files')

        # Pastikan direktori penyimpanan ada.
        # Jika 'files/' belum ada di lokasi self.storage_dir, ini akan membuatnya.
        os.makedirs(self.storage_dir, exist_ok=True)
        logging.info(f"FileInterface initialized. Storage directory: {self.storage_dir}")
        # --- AKHIR PERUBAHAN STRUKTURAL PENTING DI __init__ ---

    def _get_full_path(self, filename):
        """
        Fungsi pembantu untuk mendapatkan jalur lengkap file di dalam direktori penyimpanan.
        Ini memastikan semua operasi file menggunakan jalur yang benar dan absolut.
        """
        return os.path.join(self.storage_dir, filename)

    def list(self, params=[]):
        try:
            # Gunakan jalur lengkap untuk mencari file di dalam direktori penyimpanan.
            # os.path.basename digunakan untuk hanya mendapatkan nama file, bukan jalur lengkap.
            filelist = [os.path.basename(f) for f in glob(os.path.join(self.storage_dir, '*.*'))]
            logging.info(f"Listed files: {filelist}")
            return dict(status='OK',data=filelist)
        except Exception as e:
            logging.error(f"Error listing files: {e}")
            return dict(status='ERROR',data=str(e))

    def get(self, params=[]):
        try:
            filename = params[0]
            if not filename: # Memastikan nama file tidak kosong
                return dict(status='ERROR', data="Filename cannot be empty.")
            
            filepath = self._get_full_path(filename) # Dapatkan jalur lengkap file
            
            if not os.path.exists(filepath): # Periksa keberadaan file menggunakan jalur lengkap
                logging.warning(f"File '{filename}' not found for GET at {filepath}.")
                return dict(status='ERROR', data=f"File '{filename}' not found.")

            with open(filepath,'rb') as fp: # Buka file menggunakan jalur lengkap
                isifile = base64.b64encode(fp.read()).decode('utf-8') # Pastikan decode ke utf-8
            logging.info(f"Successfully read file '{filename}'.")
            return dict(status='OK',data_namafile=filename,data_file=isifile)
        except IndexError: # Menangani jika parameter filename tidak ada
            logging.error("GET command missing filename parameter.")
            return dict(status='ERROR', data="Filename parameter missing.")
        except Exception as e:
            logging.error(f"Error getting file '{filename}': {e}")
            return dict(status='ERROR',data=str(e))

    def upload(self, params=[]):
        try:
            filename = params[0]
            filedata = params[1]
            
            if not filename or not filedata: # Memastikan nama file dan data file tidak kosong
                return dict(status='ERROR', data="Filename or file data cannot be empty.")

            filepath = self._get_full_path(filename) # Dapatkan jalur lengkap file
            
            filebytes = base64.b64decode(filedata)
            with open(filepath, 'wb') as f: # Buka file menggunakan jalur lengkap
                f.write(filebytes)
            logging.info(f"Successfully uploaded file '{filename}'.")
            return dict(status='OK', data=f"{filename} uploaded")
        except IndexError: # Menangani jika parameter filename atau filedata tidak ada
            logging.error("UPLOAD command missing filename or filedata parameters.")
            return dict(status='ERROR', data="Filename or filedata parameters missing.")
        except Exception as e:
            logging.error(f"Error uploading file '{filename}': {e}")
            return dict(status='ERROR', data=str(e))

    def delete(self, params=[]):
        try:
            filename = params[0]
            if not filename: # Memastikan nama file tidak kosong
                return dict(status='ERROR', data="Filename cannot be empty.")

            filepath = self._get_full_path(filename) # Dapatkan jalur lengkap file
            
            if not os.path.exists(filepath): # Periksa keberadaan file menggunakan jalur lengkap
                logging.warning(f"File '{filename}' not found for DELETE at {filepath}.")
                return dict(status='ERROR', data=f"File '{filename}' not found.")

            os.remove(filepath) # Hapus file menggunakan jalur lengkap
            logging.info(f"Successfully deleted file '{filename}'.")
            return dict(status='OK', data=f"{filename} deleted")
        except IndexError: # Menangani jika parameter filename tidak ada
            logging.error("DELETE command missing filename parameter.")
            return dict(status='ERROR', data="Filename parameter missing.")
        except Exception as e:
            logging.error(f"Error deleting file '{filename}': {e}")
            return dict(status='ERROR', data=str(e))

# Bagian ini hanya berjalan jika script ini dieksekusi langsung
# (tidak saat di-import oleh file lain seperti file_protocol.py)
if __name__=='__main__':
    # Konfigurasi logging untuk pengujian lokal FileInterface
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    f = FileInterface()
    print("Daftar file awal:", f.list())
    
    # Contoh penggunaan GET (pastikan ada file 'pokijan.jpg' di folder 'files/')
    # print(f.get(['pokijan.jpg'])) 

import os
import datetime
from dotenv import load_dotenv

load_dotenv()

try:
    from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

class CloudStorageManager:
    def __init__(self, local_upload_folder):
        self.local_upload_folder = local_upload_folder
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "documents")
        self.blob_service_client = None
        self.use_azure = False

        if AZURE_AVAILABLE and self.connection_string and "YOUR_ACTUAL" not in self.connection_string:
            try:
                self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
                # Verify container exists
                container_client = self.blob_service_client.get_container_client(self.container_name)
                if not container_client.exists():
                    container_client.create_container()
                self.use_azure = True
                print("Connected successfully to Azure Blob Storage.")
            except Exception as e:
                print(f"Azure connection failed, defaulting to local storage: {e}")
                self.use_azure = False
        else:
            print("Using Local Disk Storage (Azure credentials not configured).")

    def upload_document(self, file_storage, filename):
        """Uploads file to Azure Blob or local folder. Returns (stored_filename, file_size)."""
        file_storage.seek(0, os.SEEK_END)
        file_size = file_storage.tell()
        file_storage.seek(0)

        if self.use_azure:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, blob=filename
            )
            blob_client.upload_blob(file_storage.read(), overwrite=True)
            return filename, file_size
        else:
            save_path = os.path.join(self.local_upload_folder, filename)
            file_storage.save(save_path)
            return filename, file_size

    def delete_document(self, filename):
        """Deletes a document from Azure Blob Storage or local folder."""
        if not filename:
            return False

        if self.use_azure and self.blob_service_client:
            try:
                blob_client = self.blob_service_client.get_blob_client(
                    container=self.container_name, blob=filename
                )
                if blob_client.exists():
                    blob_client.delete_blob()
                    print(f"Azure blob deleted: {filename}")
                return True
            except Exception as e:
                print(f"Failed to delete Azure blob {filename}: {e}")
                return False
        else:
            local_path = os.path.join(self.local_upload_folder, filename)
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                    print(f"Local file deleted: {filename}")
                    return True
                except OSError as e:
                    print(f"Failed to delete local file {filename}: {e}")
                    return False
        return False
    
    def get_document_access_url(self, filename):
        """Generates a secure, temporary SAS URL (15-min expiry) for Azure documents."""
        if not self.use_azure or not self.blob_service_client:
            return None

        try:
            sas_token = generate_blob_sas(
                account_name=self.blob_service_client.account_name,
                container_name=self.container_name,
                blob_name=filename,
                account_key=self.blob_service_client.credential.account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
            )
            return f"https://{self.blob_service_client.account_name}.blob.core.windows.net/{self.container_name}/{filename}?{sas_token}"
        except Exception as e:
            print(f"Error generating SAS URL: {e}")
            return None

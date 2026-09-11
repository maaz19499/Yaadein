import boto3
from botocore.client import Config
from src.config import settings

def apply_cors():
    endpoint = settings.PROD_R2_ENDPOINT_URL or "https://9a5880299d2adb341598e187d2b68746.r2.cloudflarestorage.com"
    bucket = settings.R2_BUCKET_NAME or "yaadein"
    access_key = settings.R2_ACCESS_KEY_ID
    secret_key = settings.R2_SECRET_ACCESS_KEY

    print(f"Connecting to R2 endpoint: {endpoint}")
    print(f"Target bucket: {bucket}")

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    cors_configuration = {
        "CORSRules": [
            {
                "AllowedHeaders": ["*"],
                "AllowedMethods": ["GET", "PUT", "POST", "HEAD", "DELETE"],
                "AllowedOrigins": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]
    }

    try:
        resp = s3.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors_configuration)
        print("Successfully applied CORS policy!")
        print("Response HTTP status:", resp.get("ResponseMetadata", {}).get("HTTPStatusCode"))
        
        # Verify by reading it back
        current_cors = s3.get_bucket_cors(Bucket=bucket)
        print("Verified current CORS configuration:")
        print(current_cors.get("CORSRules"))
    except Exception as e:
        print("Failed to set/get CORS:", e)

if __name__ == "__main__":
    apply_cors()

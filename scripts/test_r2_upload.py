import uuid
import requests
import boto3
from botocore.client import Config
from src.config import settings

def test_r2_upload_and_cors():
    endpoint = settings.PROD_R2_ENDPOINT_URL or "https://9a5880299d2adb341598e187d2b68746.r2.cloudflarestorage.com"
    bucket = settings.R2_BUCKET_NAME or "yaadein"
    access_key = settings.R2_ACCESS_KEY_ID
    secret_key = settings.R2_SECRET_ACCESS_KEY

    print("=" * 60)
    print("Testing Cloudflare R2 CORS & Upload Flow")
    print("=" * 60)
    print(f"Bucket: {bucket}")
    print(f"Endpoint: {endpoint}")

    # 1. Initialize boto3 S3 client
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    # 2. Generate fresh presigned PUT URL
    test_key = f"test-uploads/cors-verification-{uuid.uuid4().hex[:8]}.jpg"
    presigned_url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": bucket, "Key": test_key, "ContentType": "image/jpeg"},
        ExpiresIn=3600,
    )
    print(f"\n1. Generated fresh presigned URL for key: {test_key}")

    # 3. Simulate Browser OPTIONS Preflight Request
    browser_origin = "http://localhost:3000"
    preflight_headers = {
        "Origin": browser_origin,
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "content-type",
    }
    print(f"\n2. Emulating browser OPTIONS preflight from Origin: {browser_origin}...")
    options_res = requests.options(presigned_url, headers=preflight_headers)
    print(f"   Status Code: {options_res.status_code}")
    print(f"   Access-Control-Allow-Origin: {options_res.headers.get('Access-Control-Allow-Origin')}")
    print(f"   Access-Control-Allow-Methods: {options_res.headers.get('Access-Control-Allow-Methods')}")
    print(f"   Access-Control-Allow-Headers: {options_res.headers.get('Access-Control-Allow-Headers')}")

    if options_res.status_code not in (200, 204):
        print(f"❌ OPTIONS preflight failed with code {options_res.status_code}!")
        return False

    if not options_res.headers.get("Access-Control-Allow-Origin"):
        print("❌ Missing Access-Control-Allow-Origin in preflight response!")
        return False

    # 4. Simulate Browser PUT Upload Request
    fake_image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"  # Minimal dummy JPEG
    upload_headers = {
        "Origin": browser_origin,
        "Content-Type": "image/jpeg",
    }
    print(f"\n3. Emulating browser PUT upload with {len(fake_image_bytes)} bytes...")
    put_res = requests.put(presigned_url, data=fake_image_bytes, headers=upload_headers)
    print(f"   Status Code: {put_res.status_code}")
    print(f"   Access-Control-Allow-Origin: {put_res.headers.get('Access-Control-Allow-Origin')}")
    print(f"   ETag: {put_res.headers.get('ETag')}")

    if put_res.status_code != 200:
        print(f"❌ PUT upload failed with status {put_res.status_code}: {put_res.text}")
        return False

    # 5. Verify object exists on R2 via S3 head_object
    print(f"\n4. Verifying object landed in R2 bucket via HeadObject...")
    head = s3.head_object(Bucket=bucket, Key=test_key)
    print(f"   Object verified! Size in bucket: {head['ContentLength']} bytes")

    # 6. Cleanup test object
    s3.delete_object(Bucket=bucket, Key=test_key)
    print(f"\n5. Test object cleaned up.")
    print("\n[SUCCESS] Full browser preflight, direct upload, and CORS verified!")
    return True

if __name__ == "__main__":
    test_r2_upload_and_cors()

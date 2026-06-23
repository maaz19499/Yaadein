# Batched Multipart Upload Presigning

To support resilient media uploads over unstable network connections, we decided to use a batched presigned URL endpoint (`POST /api/v1/uploads/presign`). 

Rather than sending a single PUT for large files or making individual API requests for every file, the client requests presigned URLs in a single batch. The server dynamically inspects the file size:
1. Files under 10MB receive a single presigned URL.
2. Files over 10MB are initialized as S3 multipart uploads on Cloudflare R2, and the server returns a list of presigned URLs (one per 10MB chunk).

The client manages uploading each chunk with exponential backoff and concurrency limits, followed by a final idempotent confirmation request to verify and complete the upload.

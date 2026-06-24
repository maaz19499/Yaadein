# Split-Bucket Storage and Access Control for Media

To balance gallery loading speeds and bandwidth costs with secure monetization gating:
1. **Public Storage (Tier 1 & 2)**: Generated thumbnails (~400px WebP) and web-optimized fullscreen previews (~1600px WebP) are stored in public paths on Cloudflare R2 and served directly via CDN.
2. **Private Storage (Tier 3)**: Original high-resolution uploads are stored in a private path on Cloudflare R2.
3. **Authorized Gateway**: To download original files or request ZIP exports, clients must request a temporary (5-minute) presigned R2 download URL from FastAPI. FastAPI verifies the plan limit and overage status of the event before issuing the URL.

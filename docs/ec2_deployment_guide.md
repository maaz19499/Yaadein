# AWS EC2 Free Tier Deployment Guide (Supabase + Upstash Stack)

This document provides a streamlined, zero-cost deployment guide for **Yaadein** on **AWS EC2 Free Tier**, leveraging managed free tiers for Database (**Supabase**) and Cache/Message Broker (**Upstash Redis**).

---

## 1. Production Architecture Overview

By offloading PostgreSQL and Redis to managed Cloud Free Tiers, your EC2 instance runs **zero database/broker overhead**, preserving 100% of the 1 GB RAM for your FastAPI application and Celery background workers.

```
                  ┌───────────────────────────────────────────┐
                  │   AWS EC2 Free Tier (t2.micro / t3.micro)  │
                  │   ┌───────────────────────────────────┐   │
                  │   │ Nginx (Reverse Proxy Port 80/443) │   │
                  │   └─────────────────┬─────────────────┘   │
                  │                     │                     │
                  │         ┌───────────┴───────────┐         │
                  │         │  yaadein-api (8000)   │         │
                  │         └───────────┬───────────┘         │
                  │                     │ Task Enqueue        │
                  │         ┌───────────v───────────┐         │
                  │         │    yaadein-worker     │         │
                  │         └───────────┬───────────┘         │
                  └─────────────────────┼─────────────────────┘
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             │                          │                          │
             v                          v                          v
┌─────────────────────────┐┌─────────────────────────┐┌─────────────────────────┐
│ Supabase PostgreSQL     ││ Upstash Redis           ││ Cloudflare R2 / S3      │
│ (with pgvector extension)││ (TLS Message Broker)    ││ (Media Object Storage)  │
└─────────────────────────┘└─────────────────────────┘└─────────────────────────┘
```

---

## 2. Step-by-Step EC2 Deployment Framework

---

### Step 1: Launch a Free Tier Eligible EC2 Instance

1. Log in to the **AWS Management Console** and open **EC2 Dashboard**.
2. Click **Launch Instance**.
3. **Name**: `yaadein-backend-prod`.
4. **AMI**: **Ubuntu Server 24.04 LTS** (Ensure *"Free tier eligible"* tag).
5. **Instance Type**: `t2.micro` (or `t3.micro` depending on AWS region).
6. **Key Pair**:
   * Click **Create new key pair**.
   * Name: `yaadein-ec2-key.pem`.
   * Save securely (e.g., `~/.ssh/yaadein-ec2-key.pem`).
7. **Network Settings (Security Group)**:
   * **SSH (Port 22)**: From **My IP** (recommended for security).
   * **HTTP (Port 80)**: From `0.0.0.0/0` (Anywhere).
   * **HTTPS (Port 443)**: From `0.0.0.0/0` (Anywhere).
8. **Storage**: Set volume size to **30 GiB** (General Purpose SSD `gp3`).
9. Click **Launch Instance**.

---

### Step 2: Connect to Your Instance via SSH

Open your terminal or Git Bash:

```bash
# Set key permissions
chmod 400 ~/.ssh/yaadein-ec2-key.pem

# Connect via Public IP
ssh -i ~/.ssh/yaadein-ec2-key.pem ubuntu@13.203.74.97
```

---

### Step 3: Server Optimization (2GB Swap Setup)

Run the following commands on the EC2 server to prevent Out-Of-Memory (OOM) crashes:

```bash
# Update Ubuntu system
sudo apt update && sudo apt upgrade -y

# Allocate 2GB Swap space
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make swap permanent across reboots
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Verify swap memory status
free -h
```

---

### Step 4: Install Docker & Docker Compose

```bash
# Install Docker and Docker Compose plugin
sudo apt install -y docker.io docker-compose-v2

# Allow ubuntu user to execute docker commands without sudo
sudo usermod -aG docker ubuntu
newgrp docker

# Verify installation
docker --version
docker compose version
```

---

### Step 5: Clone Repository & Set Production Environment Variables

1. Clone your repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Yaadein.git
   cd Yaadein
   ```

2. Create `.env` file on the server:
   ```bash
   nano .env
   ```

3. Paste your cloud service credentials:
   ```ini
   ENVIRONMENT=production

   # Supabase PostgreSQL Connection
   SUPABASE_DATABASE_URL=postgresql://postgres.xxx:your_password@aws-0-us-east-1.pooler.supabase.com:6543/postgres

   # Upstash Redis Connection (rediss:// for TLS)
   UPSTASH_REDIS_URL=rediss://default:your_upstash_token@your-redis.upstash.io:6379

   # Supabase JWT Secret
   SUPABASE_JWT_SECRET=your_supabase_jwt_secret

   # AWS Rekognition & Storage
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your_aws_key
   AWS_SECRET_ACCESS_KEY=your_aws_secret

   # Cloudflare R2 / S3 Storage
   PROD_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
   R2_BUCKET_NAME=yaadein-media
   R2_ACCESS_KEY_ID=your_r2_key
   R2_SECRET_ACCESS_KEY=your_r2_secret
   ```

---

### Step 6: Deploy Services via Docker Compose

Deploy the API and Worker using the production compose file:

```bash

# Rebuild images without cache
docker compose -f docker-compose.prod.yml build --no-cache

# Build and launch API & Worker containers in background
docker compose -f docker-compose.prod.yml up -d --build

# Verify running container status
docker compose -f docker-compose.prod.yml ps

# Inspect logs
docker compose -f docker-compose.prod.yml logs -f
```

*(Note: Alembic database migrations run automatically on container startup during entrypoint).*

---

### Step 7: Configure Nginx & Free SSL (Certbot)

1. Install Nginx:
   ```bash
   sudo apt install -y nginx
   ```

2. Create Nginx site configuration:
   ```bash
   sudo nano /etc/nginx/sites-available/yaadein
   ```

3. Paste reverse proxy configuration:
   ```nginx
   server {
       listen 80;
       server_name <YOUR_EC2_PUBLIC_IP_OR_DOMAIN>;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

4. Enable site configuration & restart Nginx:
   ```bash
   sudo ln -s /etc/nginx/sites-available/yaadein /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t
   sudo systemctl restart nginx
   ```

5. *(Optional)* **Enable Free SSL Certificate (Let's Encrypt)** if pointing a domain:
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d yourdomain.com
   ```

---

## 3. Maintenance & Updating Code

To deploy code updates in the future without CodeDeploy:

```bash
cd /home/ubuntu/Yaadein
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build
```

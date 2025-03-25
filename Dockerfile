FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .
COPY .env.docker .env

# Expose the app port
EXPOSE 8000

# Default command
# CMD ["python", "app/main.py"]

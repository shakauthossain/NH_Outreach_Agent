# Use an official lightweight Python image
FROM python:3.10-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create app directory and Hugging Face cache
# RUN mkdir -p /app /app/hf_cache /app/uploaded_csvs

# Set the working directory
WORKDIR /app

# Copy dependency definitions first (for Docker caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

# Copy the entire project (including auth/ folder and static/)
COPY . .

# Set full permissions for static folder
RUN chmod -R 777 /app/static
RUN chmod -R 777 /app/uploaded_csvs
RUN chmod +x /app/start.sh

# Expose the port Hugging Face Spaces expects
EXPOSE 8000

# Run the FastAPI app via Uvicorn
CMD ["/app/start.sh"]
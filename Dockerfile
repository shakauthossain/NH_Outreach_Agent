# Use an official lightweight Python image
FROM python:3.10-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create app directory and Hugging Face cache
RUN mkdir -p /app /app/hf_cache

# Set the working directory
WORKDIR /app

# Copy dependency definitions first (for Docker caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project (including auth/ folder and static/)
COPY . .

# Set full permissions for static folder
RUN chmod -R 777 /app/static

# Expose the port Hugging Face Spaces expects
EXPOSE 7860

# Run the FastAPI app via Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
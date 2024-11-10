# Use a base image with Python
FROM python:3.12-slim

# Install required packages for OpenCV
RUN apt-get update && apt-get install -y libgl1

# Set working directory and copy application files
WORKDIR /app
COPY . /app

# Install Python dependencies
RUN pip install -r requirements.txt

# Set the command to run your application
CMD ["python", "app.py"]

# Add these if you need camera support
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0
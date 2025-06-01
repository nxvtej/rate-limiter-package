# Dockerfile

# Use a slim Python image for smaller size
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if any (e.g., for some Python packages)
# In this case, not strictly necessary for FastAPI/Redis but good practice
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml first to leverage Docker cache
# This line now only copies pyproject.toml
COPY pyproject.toml ./

# Install project dependencies from pyproject.toml
# pip install . will install dependencies defined in pyproject.toml's [project] section
RUN pip install .

# Copy the rest of your application code
COPY . .

# Expose the port your FastAPI app runs on
EXPOSE 8000

# Set the default command for this image (can be overridden)
CMD ["python", "-m", "pytest"]
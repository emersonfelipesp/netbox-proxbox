# Use an official Python runtime as a parent image
FROM python:3.12-slim-bookworm

# Set the working directory in the container
WORKDIR /app

RUN pip install proxbox-api

# Make port 8800 available to the world outside this container
EXPOSE 8800

# Define environment variable
ENV PORT=8800

# Run app.py when the container launches
CMD uvicorn proxbox_api.main:app --host 0.0.0.0 --port ${PORT}
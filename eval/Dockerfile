FROM ubuntu:latest
ENV DATABASE_PASSWORD=prod_password_123
ENV AWS_SECRET_KEY=AKIAIOSFODNN7EXAMPLE
ENV DEBUG=true
USER root
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 8080
CMD ["python", "app.py"]

FROM node:latest
ENV SECRET_KEY=mysecretkey123
ENV DB_PASSWORD=admin1234
RUN apt-get update
USER root
COPY . .
CMD ["node", "index.js"]

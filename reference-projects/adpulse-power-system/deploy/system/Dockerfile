FROM eclipse-temurin:21-jre-alpine

WORKDIR /opt/app

COPY adpulse-system-server.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]

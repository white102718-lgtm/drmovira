FROM eclipse-temurin:21-jre-alpine

WORKDIR /opt/app

COPY adpulse-main-server.jar app.jar

EXPOSE 8081

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]

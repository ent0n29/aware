# Multi-stage Dockerfile for Java Spring Boot services
# Usage: docker build --build-arg SERVICE=executor-service -f Dockerfile.java -t aware/executor ..

ARG SERVICE=strategy-service

# Stage 1: Build
FROM maven:3.9-amazoncorretto-21 AS builder
ARG SERVICE

WORKDIR /build

# Copy parent POM and all modules for dependency resolution
COPY pom.xml .
COPY polybot-core/pom.xml polybot-core/
COPY executor-service/pom.xml executor-service/
COPY strategy-service/pom.xml strategy-service/
COPY ingestor-service/pom.xml ingestor-service/
COPY analytics-service/pom.xml analytics-service/

# Download dependencies (cached layer)
RUN mvn dependency:go-offline -B -pl ${SERVICE} -am

# Copy source code
COPY polybot-core/src polybot-core/src
COPY ${SERVICE}/src ${SERVICE}/src

# Build the specific service
RUN mvn package -DskipTests -pl ${SERVICE} -am

# Stage 2: Runtime
FROM amazoncorretto:21-alpine
ARG SERVICE

WORKDIR /app

# Copy JAR from builder
COPY --from=builder /build/${SERVICE}/target/*.jar app.jar

# Environment defaults
ENV JAVA_OPTS="-Xmx512m -Xms256m"
ENV SPRING_PROFILES_ACTIVE=production

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]

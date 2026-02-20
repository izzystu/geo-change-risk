# Geo Change Risk API - Multi-stage Docker build
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copy project files for restore
COPY GeoChangeRisk.Contracts/GeoChangeRisk.Contracts.csproj GeoChangeRisk.Contracts/
COPY GeoChangeRisk.Data/GeoChangeRisk.Data.csproj GeoChangeRisk.Data/
COPY GeoChangeRisk.Api/GeoChangeRisk.Api.csproj GeoChangeRisk.Api/

# Restore dependencies
RUN dotnet restore GeoChangeRisk.Api/GeoChangeRisk.Api.csproj

# Copy all source files
COPY . .

# Publish release build
RUN dotnet publish GeoChangeRisk.Api/GeoChangeRisk.Api.csproj \
    -c Release \
    -o /app/publish

# Runtime image
FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app

COPY --from=build /app/publish .

# App Runner default port
ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

ENTRYPOINT ["dotnet", "GeoChangeRisk.Api.dll"]

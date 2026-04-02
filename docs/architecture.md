# MUEFS Architecture

## System Overview

```
                    ┌─────────────┐
                    │   Frontend   │
                    │  React/Vite  │
                    │  Port 3000   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  API Gateway │
                    │   FastAPI    │
                    │  Port 8000   │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
   │  PostgreSQL  │ │    Redis    │ │    MinIO    │
   │   Database   │ │ Cache/Queue │ │  Documents  │
   │  Port 5432   │ │  Port 6379  │ │  Port 9000  │
   └─────────────┘ └──────┬──────┘ └─────────────┘
                          │
                   ┌──────▼──────┐
                   │   Celery    │
                   │   Worker    │
                   │ Doc Process │
                   └─────────────┘
```

## Key Design Decisions

1. **Centralized with Adapter Layer**: Single portal for all courts, with CMS adapters
   for JIS, Tyler Odyssey, and other systems (Texas/Florida hybrid model)

2. **Microservice-Ready Monolith**: Built as a well-structured monolith that can be
   decomposed into microservices as scale demands

3. **Standards-First**: OASIS LegalXML ECF 4.01 compliance, PDF/A documents,
   SHA-256 integrity verification

4. **MCR 1.109 Compliance**: Text-searchable PDFs, electronic signatures,
   PII redaction warnings, electronic service

## Filing Workflow

```
DRAFT → SUBMITTED → UNDER_REVIEW → ACCEPTED (creates Case)
                                  → REJECTED (with reason)
                                  → RETURNED → SUBMITTED (resubmit)
```

## CMS Integration Pattern

```
Filing Accepted → CMS Adapter (abstract) → JIS Adapter
                                         → Tyler Adapter
                                         → Generic REST Adapter
```

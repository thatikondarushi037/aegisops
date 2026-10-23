
# Payment Service — Troubleshooting Runbook

## Symptoms
- Elevated payment transaction error rate
- Increased API response latency
- Payment requests timing out

## Possible causes
- Database connection pool exhaustion
- Slow database queries
- Downstream payment provider errors
- Recent deployment regressions

## Investigation steps
1. Examine application error logs.
2. Check database connection pool metrics.
3. Inspect slow queries.
4. Check downstream provider health.
5. Review recent deployments.

## Safety
Do not restart services, change database settings,
or roll back deployments without human approval.

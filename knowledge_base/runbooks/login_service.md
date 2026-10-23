
# Login Service — Troubleshooting Runbook

## Symptoms
- Users cannot log in
- Authentication requests return errors
- Login requests experience high latency

## Possible causes
- Authentication token validation failures
- Identity provider unavailable
- Redis session store connection issues
- Incorrect authentication configuration

## Investigation steps
1. Examine authentication service logs.
2. Check identity provider health.
3. Inspect token validation errors.
4. Verify Redis session store connectivity.
5. Review authentication configuration changes.

## Safety
Do not reset credentials or rotate secrets without
authorization and an approved recovery procedure.

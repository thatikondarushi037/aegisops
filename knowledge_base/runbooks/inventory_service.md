
# Inventory Service — Troubleshooting Runbook

## Symptoms
- Inventory updates fail
- Stock quantities appear incorrect
- Product availability requests time out

## Possible causes
- Database transaction conflicts
- Inventory event queue backlog
- Message broker connectivity problems
- Stock synchronization failures

## Investigation steps
1. Inspect inventory service error logs.
2. Check pending messages in the event queue.
3. Verify message broker connectivity.
4. Examine database transaction failures.
5. Review stock synchronization jobs.

## Safety
Do not manually alter stock quantities or replay events
without approval and a verified recovery plan.

Deployment notification for ${{ data.service }}:

**Environment**: ${{ data.environment }}
**Version**: ${{ data.version }}
**Status**: ${{ data.status }}
**Deployed by**: ${{ data.deployer }}
**Timestamp**: ${{ data.timestamp }}

**Changes**:
${{ data.changes }}

**Health Checks**:
- API Status: ${{ data.health.api }}
- Database: ${{ data.health.database }}
- Cache: ${{ data.health.cache }}

Please monitor this deployment and:
1. Verify all health checks pass
2. Watch for error rate changes
3. Report any anomalies immediately
4. Confirm rollback procedure if needed

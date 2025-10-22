Production Deployment Request from ${{ data.system }}:

**Service**: ${{ data.service }}
**Environment**: ${{ data.environment }}
**Version**: ${{ data.version }}
**Requester**: ${{ data.requester }}

**Deployment Steps**:
1. Verify all pre-deployment checks are complete
2. Create backup of current production state
3. Deploy new version to production servers
4. Run smoke tests and health checks
5. Monitor system metrics for 15 minutes
6. Document deployment in change log

This is a production deployment request. Please acknowledge receipt and confirm deployment parameters.

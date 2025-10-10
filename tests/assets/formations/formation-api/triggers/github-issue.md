New GitHub issue from ${{ data.repository }}:

**Issue #${{ data.issue.number }}**: ${{ data.issue.title }}

**Author**: ${{ data.issue.author }}
**State**: ${{ data.issue.state }}
**Labels**: ${{ data.issue.labels }}

**Description**:
${{ data.issue.body }}

Please analyze this issue and provide:
1. A summary of the problem
2. Potential impact assessment
3. Suggested priority level
4. Relevant code areas to investigate

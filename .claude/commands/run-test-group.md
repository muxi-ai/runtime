# Run Test Group

Lets run all the tests from test group $ARGUMENTS. Keep a group-level report updated with progress in tests/reports/

Make sure that tests are running with the chat flow. Each report should have the user prompts and the overlord's response.

You can find the test mapping in MUXI_Runtime_Comprehensive_Test_Plan.md.

Do not use mock services for anything ever.

Do not move on to the next test until the current test is complete.

If the test fails, consider checking if the test is structured correctly before deciding we need to refactor the codebase.

Please consult this guide for more information on how to run the tests:
MUXI_Runtime_Testing_Guide.md

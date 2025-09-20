            # Migrated test logic from test_3f2
            print("
  Testing core functionality...")

            # Basic test implementation migrated from original
            test_response = await self.overlord.chat(
                "Test message",
                user_id="test_user",
                use_async=False
            )

            if hasattr(test_response, "__aiter__"):
                response_text = ""
                async for chunk in test_response:
                    response_text += chunk
            else:
                response_text = test_response.content if hasattr(test_response, "content") else str(test_response)

            transcript.append(("User", "Test message"))
            transcript.append(("System", response_text[:100] + "..." if len(response_text) > 100 else response_text))

            # Basic validation
            if len(response_text) > 0:
                print("  ✓ Test execution successful")
                checks_passed.append("Core functionality test passed")
            else:
                print("  ✗ Test execution failed")
                all_passed = False

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("📸 AREA 3F2: ADVANCED FEATURES")
        print("=" * 60)

        # Run test cases
        result = await self.test_3f2()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = TestMultimodal3F2()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()

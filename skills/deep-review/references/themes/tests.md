# Theme: tests

Judge whether the tests would catch the bugs that matter in this code.

Look for:
- Changed or new behaviour with no test, especially branching logic, error
  paths, edge cases and bug fixes without a regression test.
- Tests that would pass even if the code were wrong: no assertions,
  asserting on mocks only, asserting the implementation instead of the
  behaviour, snapshot updates accepted blindly.
- Tests weakened by the change: deleted or skipped tests, loosened
  assertions, increased tolerances, broad exception catching.
- Fragile tests: dependence on time, order, randomness, network, shared
  state, or sleeps.
- Over-mocking that hides integration problems the change is likely to
  have.
- Test data that does not exercise the interesting cases (empty, boundary,
  unicode, large).

For missing tests, name the specific case and the assertion that should
exist. Do not flag:
- Missing tests for trivial code (getters, pure wiring) or generated code.
- Coverage percentages as such.

# Verify Before Claiming

Never make confident claims about runtime behavior, safety, or side effects based on general assumptions. Always verify against the actual code first.

## The pattern to avoid

1. User asks "will X break if I do Y?"
2. Agent reasons from a general mental model ("processes load code at startup, so editing files is safe")
3. Agent gives a confident answer without reading the specific code
4. The answer is wrong because the specific implementation differs from the general case

## The required behavior

1. User asks "will X break if I do Y?"
2. Agent reads the relevant code to verify
3. Agent answers based on what the code actually does, citing specifics
4. If unable to verify, say "I'm not sure — let me check" rather than guessing

This applies to any claim about: process safety, backwards compatibility, performance impact, concurrency behavior, deployment effects, or any other system behavior where being wrong has consequences.

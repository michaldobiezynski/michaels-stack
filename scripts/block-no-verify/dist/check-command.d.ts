import type { CheckResult } from './check-result.js';
/**
 * Checks a command input for --no-verify flag usage or hooks path override
 *
 * @param input - The command input to check (typically from stdin in Claude Code hooks)
 * @returns CheckResult indicating whether the command should be blocked
 */
export declare function checkCommand(input: string): CheckResult;
//# sourceMappingURL=check-command.d.ts.map
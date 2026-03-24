import type { InputFormat } from './input-format.js';
import type { ParseResult } from './parse-result.js';
/**
 * Parses input according to the specified format
 *
 * @param input - Raw input string
 * @param format - Input format to use (defaults to 'auto' if not provided)
 * @returns ParseResult with extracted command and detected format
 *
 * @example
 * // Plain text
 * parseInput('git commit --no-verify')
 * // => { command: 'git commit --no-verify', format: 'plain' }
 *
 * @example
 * // Claude Code format
 * parseInput('{"tool_input":{"command":"git commit --no-verify"}}', 'claude-code')
 * // => { command: 'git commit --no-verify', format: 'claude-code' }
 *
 * @example
 * // Auto-detect JSON
 * parseInput('{"command":"git commit --no-verify"}')
 * // => { command: 'git commit --no-verify', format: 'json' }
 */
export declare function parseInput(input: string, format?: InputFormat): ParseResult;
//# sourceMappingURL=parse-input.d.ts.map
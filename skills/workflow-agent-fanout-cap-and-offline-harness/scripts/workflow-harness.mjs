/**
 * Run a Claude Code Workflow script offline, with the runtime globals stubbed, so its
 * sub-agent fan-out can be asserted without spawning a single real agent.
 *
 * Workflow scripts are plain JS that rely on injected globals (args, agent, parallel,
 * pipeline, phase, log) and finish with a top-level `return`, so they cannot be imported.
 * This wraps the source in an async IIFE and evaluates it with stubs supplied.
 *
 *   import { runWorkflow } from './workflow-harness.mjs'
 *
 *   const { result, calls, logs, phases } = await runWorkflow('/path/to/wf.js', {
 *     args: { base: 'origin/master' },
 *     onAgent: (prompt, opts, index) =>
 *       opts.phase === 'Review' ? { lens: opts.label, findings: [] } : { verdicts: [] },
 *   })
 *   console.log(calls.length)                       // exact agent count
 *   console.log(calls.map((c) => c.label))          // what each one was asked to do
 */
import { readFileSync } from 'node:fs'

/**
 * @param {string} path                Absolute path to the workflow script.
 * @param {object} options
 * @param {any}    [options.args]      Value exposed to the script as the `args` global.
 * @param {(prompt: string, opts: object, index: number) => any} options.onAgent
 *        Stub for each agent() call. Return data matching the schema the script expects,
 *        or throw to simulate an agent dying so error paths can be asserted.
 * @param {boolean} [options.sequential=true]
 *        Run parallel() thunks one at a time. Keeps `calls` deterministically ordered.
 * @returns {Promise<{result: any, calls: Array, logs: string[], phases: string[]}>}
 */
export async function runWorkflow(path, { args = {}, onAgent, sequential = true } = {}) {
  if (typeof onAgent !== 'function') throw new TypeError('runWorkflow needs an onAgent stub')

  // `export const meta` is valid in a module but not inside a function body.
  const source = readFileSync(path, 'utf8').replace(/^export const meta =/m, 'const meta =')

  const calls = []
  const logs = []
  const phases = []

  const agent = async (prompt, opts = {}) => {
    const index = calls.length
    calls.push({ index, label: opts.label, phase: opts.phase, model: opts.model, effort: opts.effort, prompt })
    return onAgent(prompt, opts, index)
  }

  // Mirrors the real contract: a thunk that throws resolves to null rather than rejecting.
  const settle = async (thunk) => {
    try {
      return await thunk()
    } catch {
      return null
    }
  }
  const parallel = async (thunks) => {
    if (sequential) {
      const out = []
      for (const t of thunks) out.push(await settle(t))
      return out
    }
    return Promise.all(thunks.map(settle))
  }

  const pipeline = async (items, ...stages) => {
    const out = []
    for (const [i, item] of items.entries()) {
      let value = item
      try {
        for (const stage of stages) value = await stage(value, item, i)
        out.push(value)
      } catch {
        out.push(null)
      }
    }
    return out
  }

  const workflow = async () => {
    throw new Error('nested workflow() is not stubbed by this harness')
  }
  const budget = { total: null, spent: () => 0, remaining: () => Infinity }

  const body = `return (async () => {\n${source}\n})()`
  const fn = new Function('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', 'workflow', 'budget', body)
  const result = await fn(
    args,
    agent,
    parallel,
    pipeline,
    (t) => phases.push(t),
    (m) => logs.push(m),
    workflow,
    budget,
  )

  return { result, calls, logs, phases }
}

/** Assert no prompt tells its agent to fan out further. Returns the offending calls. */
export function promptsEncouragingFanout(calls) {
  const encouraging = /team of agents|use a team|spawn a team|spawn (?:several|multiple|a few) (?:sub-?)?agents/i
  return calls.filter((c) => encouraging.test(c.prompt))
}

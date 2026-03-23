# Global Claude Code Rules

## Architecture & Design Diagrams

When discussing **system architecture**, **app design**, **feature design**, or any topic involving components, data flow, services, or technical structure, **proactively suggest creating a draw.io diagram** using the `/drawio` skill.

This applies when:
- Designing or discussing a new system, service, or feature
- Explaining how components interact or data flows between them
- Planning infrastructure, microservices, or API designs
- Reviewing or refactoring existing architecture
- Any conversation where a visual diagram would clarify the discussion

Suggest the diagram naturally in context, e.g. "Want me to draw a diagram of this architecture?" — don't force it if the topic is trivially simple or the user is clearly not interested.

---

## Primary Directive: Clarify Before Acting

Before planning, implementing, or modifying any code, you MUST first ask clarifying questions to ensure you understand the requirements fully.

### Workflow

#### 1. Receive Task → Analyse for Gaps
When given a task, identify:
- Ambiguous requirements
- Implicit assumptions you're making
- Technical decisions that could go multiple ways
- Missing context about existing codebase

#### 2. Ask 2-5 Clarifying Questions

Structure your questions around:

**Requirements Clarity**
- What's the expected behaviour for edge cases?
- What inputs/outputs are expected?
- Are there specific error states to handle?

**Technical Direction**
- Preferred patterns or approaches?
- Any existing conventions in the codebase to follow?
- Performance/scalability requirements?

**Integration Context**
- How does this fit with existing code?
- Are there dependencies or APIs I should be aware of?
- What's the deployment target?

**Definition of Done**
- How should this be tested?
- Are there specific acceptance criteria?
- Any documentation requirements?

#### 3. Summarise Understanding
After receiving answers, confirm your understanding:
> "Got it. I'll build [X] that [does Y], handling [Z]. I'll use [approach]. Let me know if that's correct, then I'll proceed."

#### 4. Only Then: Plan and Implement
Once confirmed, proceed with:
1. Brief implementation plan
2. Code implementation
3. Suggestions for testing

### Question Quality

**Ask questions that:**
- Would change your implementation based on the answer
- Can't be reasonably inferred from context
- Are specific enough to get actionable answers

**Don't ask about:**
- Things explicitly stated in the prompt
- Trivial details that don't affect the solution
- More than 5 things at once

### Skip Clarification Only When:
- Task is trivially simple and unambiguous
- Following up on already-clarified work
- Explicitly told "just do it" or given exhaustive specs

### Example Interaction

**User:** Add authentication to the API

**You:** Before I implement authentication, a few questions:

1. **Auth method**: JWT tokens, session-based, or OAuth? Any existing auth infrastructure?
2. **Scope**: All endpoints or specific ones? Any public endpoints to exclude?
3. **User storage**: Where are users/credentials stored? Existing user model?
4. **Requirements**: Password requirements, rate limiting, refresh tokens needed?

Once you clarify, I'll outline the approach and implement it.

---

## Documentation & Learning Resources

When working with technologies, frameworks, or libraries (Erlang, Elixir, Kafka, Terraform, CloudFormation, Go, Python, TypeScript, React, etc.), use the Context7 MCP tool to access official documentation.

**Always consult Context7 for:**
- API references and best practices for the technologies being used
- Configuration options and proper usage patterns
- Framework-specific conventions and idioms
- Up-to-date syntax and feature availability

**Guidelines:**
- Use Context7 proactively when you need to verify implementation details or explore framework capabilities
- Prefer official documentation from Context7 over relying on training data that may be outdated
- When suggesting solutions, reference the documentation you've consulted to provide context

---

## British English Standard

Always use British English spelling, grammar, and conventions in all code comments, documentation, variable names, and text output.

### Spelling
- Use British spellings: colour, organise, centre, travelling, programme, analyse, behaviour, favour, honour, labour, defence, licence (noun), license (verb), practise (verb), practice (noun)
- Use -ise endings: organise, realise, finalise (not -ize)
- Use -our endings: colour, favour, behaviour (not -or)
- Use -re endings: centre, metre, litre (not -er)
- Double consonants: travelling, modelling, cancelled (not traveling, modeling, canceled)

### Terminology
- Use British terms in comments and documentation:
  - lift (not elevator)
  - lorry (not truck)
  - mobile (not cell phone)
  - postcode (not zip code)
  - maths (not math)
  - aluminium (not aluminum)

### Punctuation
- Use single quotation marks for strings and text where appropriate
- Place punctuation logically (outside quotes unless part of quoted material)

### Date Formatting
- Use DD/MM/YYYY format: 31/10/2025
- Or ISO 8601: 2025-10-31

This applies to all generated code comments, documentation, commit messages, README files, and user-facing text.

---

## Code Comments and Documentation

### Avoid Redundant Comments

1. **Do NOT add obvious section comments:**
   - ❌ `// Helper functions`
   - ❌ `// Constants`
   - ❌ `// Imports`
   - ❌ `// State variables`
   - ❌ `// Component`
   - ❌ `// Exports`

2. **Do NOT create documentation files unless explicitly requested:**
   - ❌ README.md (unless user asks)
   - ❌ CHANGELOG.md
   - ❌ CONTRIBUTING.md
   - ❌ API.md or similar docs
   - Only create .md files when the user specifically requests them

3. **Only add comments that provide value:**
   - ✅ Explain WHY something is done (not WHAT)
   - ✅ Document complex algorithms or business logic
   - ✅ Warn about gotchas or non-obvious behaviour
   - ✅ Add TODO or FIXME with context
   - ✅ Explain workarounds or hacks

4. **Good vs Bad Examples:**

**Bad - Redundant:**
```javascript
// Helper functions
function formatDate(date) { ... }
function calculateTotal(items) { ... }

// Constants
const MAX_ITEMS = 100;
```

**Good - Valuable:**
```javascript
// Using UTC to avoid timezone issues when comparing dates across regions
function formatDate(date) { ... }

// Note: Total excludes tax because tax is calculated at checkout
function calculateTotal(items) { ... }
```

### Key Principle
**Let the code speak for itself.** Only comment when you're adding information that isn't obvious from reading the code.

---

## Unit Test Selectors

### Priority: Use data-testid Attributes

When writing or modifying unit tests:

1. **Always prefer `data-testid`** for selecting elements in tests
   - Use `getByTestId`, `findByTestId`, `queryByTestId` (React Testing Library)
   - Use `cy.get('[data-testid="..."]')` (Cypress)
   - Use `page.getByTestId('...')` (Playwright)

2. **If `data-testid` doesn't exist:**
   - **ADD IT** to the component/element being tested
   - Place it on the most semantic/relevant element
   - Use descriptive, kebab-case naming: `data-testid="submit-button"`, `data-testid="user-profile-card"`

3. **Naming conventions for data-testid:**
   - Be descriptive and specific: `login-form-submit-button` not just `button`
   - Use component context: `header-nav-menu`, `footer-copyright-text`
   - For lists: `user-list-item-{index}` or `product-card-{id}`

4. **Only use className as a fallback when:**
   - You cannot modify the source code (third-party libraries)
   - The component is from an external package
   - It's truly impossible to add data-testid
   - Document with a comment why className is used

5. **Avoid:**
   - ❌ Selecting by className for components you control
   - ❌ Selecting by element tag names alone (`button`, `div`)
   - ❌ Complex CSS selectors that are brittle
   - ❌ Selecting by text content when data-testid is possible

### Examples

**Good:**
```javascript
// Component
<button data-testid="login-submit-button">Login</button>

// Test
const submitButton = screen.getByTestId('login-submit-button');
```

**Acceptable (with comment):**
```javascript
// Using className because this is from a third-party library
const thirdPartyModal = document.querySelector('.third-party-modal-class');
```

**Bad:**
```javascript
// ❌ Don't do this when you can add data-testid
const button = document.querySelector('.btn-primary');
```

### Benefits
- Tests are decoupled from styling changes
- Clear intent in what's being tested
- More maintainable and readable tests
- No conflicts when CSS classes change

---

## UI Component Library Usage

### Priority: Use Existing UI Libraries First

When styling components or creating UI elements:

1. **Check for existing UI libraries** in the project (package.json dependencies):
   - Material-UI (@mui/material)
   - Ant Design (antd)
   - Chakra UI
   - Mantine
   - Shadcn/ui
   - Or other component libraries

2. **If a UI library is present:**
   - ALWAYS use the library's components and styling system first
   - Use the library's theme/design tokens for colours, spacing, typography
   - Leverage built-in props for styling (e.g., `sx` prop in MUI, className patterns in Ant Design)
   - Only write custom CSS when the library doesn't provide the needed functionality

3. **Avoid:**
   - Creating custom CSS files or styled-components when library components exist
   - Reinventing components that the library already provides
   - Mixing custom styles that conflict with the library's design system

4. **Examples:**
   - ✅ Use `<Button variant="contained" color="primary">` (MUI)
   - ✅ Use `<Button type="primary">` (Ant Design)
   - ❌ Creating custom button styles with CSS

5. **Custom CSS is acceptable for:**
   - Project-specific layouts not covered by the library
   - Minor adjustments that can't be achieved with library props
   - Animation or complex interactions not provided by the library

Always maintain consistency with the library's design system and patterns.

---

## Git Commit Messages

### Format

```
<type>: (<scope>) <subject>
```

### Components

1. **Type**: The category of change
   - `feat`: New feature or enhancement
   - `fix`: Bug fix
   - `refactor`: Code restructuring without changing behaviour
   - `chore`: Maintenance tasks, dependency updates
   - `docs`: Documentation changes
   - `test`: Adding or updating tests
   - `style`: Code formatting, whitespace changes

2. **Scope**: The file or module affected (in parentheses)
   - Use the filename without extension for single-file changes
   - Use the module/folder name for multi-file changes
   - Examples: `(playersReducer)`, `(wsConnection)`, `(players)`, `(auth)`

3. **Subject**: Clear, concise description of what changed
   - Start with lowercase
   - Use imperative mood ("add" not "added")
   - No period at the end
   - Max 72 characters for entire message
   - Focus on WHAT and WHY, not HOW

### Examples

✅ Good:
- `feat: (playersReducer) use phase-specific market IDs for price retrieval`
- `feat: (wsConnection) add phase-specific market ID subscription for players`
- `fix: (auth) resolve token refresh on expired sessions`
- `refactor: (utils) extract validation logic to separate function`

❌ Bad:
- `Updated files` (too vague, no type or scope)
- `feat: added new feature to playersReducer.ts` (includes extension, not concise)
- `fix: Fixed a bug.` (period at end, not specific)
- `feat (playerReducer) Added support for market IDs` (wrong format, capitalised)

### Critical Rules

- **NEVER include Claude as a co-author** - Do not add "Co-Authored-By: Claude" or any variation to commit messages
- **NEVER include "Generated with Claude Code"** or similar AI attribution in commits
- Keep the entire message under 72 characters
- If more detail is needed, add a blank line and description in the commit body
- One logical change per commit
- Scope should match the primary file/module affected

---

## Pull Request Review

When reviewing pull requests, follow this structured approach:

### Review Checklist

#### 1. Bug Prevention & Code Correctness
- **Logic errors**: Check for off-by-one errors, incorrect conditionals, missing edge cases
- **Null/undefined handling**: Verify proper null checks and error handling
- **Race conditions**: Look for potential concurrency issues, async/await problems
- **Memory leaks**: Check for unclosed resources, event listeners, subscriptions
- **Type safety**: Ensure types are correct and used consistently
- **Error handling**: Verify try-catch blocks, error propagation, and user-facing error messages

#### 2. Code Structure & Quality
- **Single Responsibility**: Each function/class should do one thing well
- **DRY principle**: Identify and flag code duplication
- **Naming conventions**: Check for clear, descriptive variable and function names
- **Function length**: Flag functions longer than 50 lines for potential refactoring
- **Complexity**: Identify overly complex logic that could be simplified

#### 3. Testing Requirements
- **Test coverage**: Verify tests exist for new functionality
- **Edge cases**: Ensure tests cover edge cases and error scenarios
- **Test quality**: Review test names, assertions, and maintainability
- **Mocking**: Ensure external dependencies are properly mocked

#### 4. Repository Standards
- **Code style**: Check adherence to linting rules and formatting conventions
- **File organisation**: Verify files are in correct directories following project structure
- **Import statements**: Check for unused imports, correct import paths
- **Dependencies**: Flag new dependencies that might be unnecessary

#### 5. Performance & Security
- **Performance**: Identify potential bottlenecks, expensive operations in loops
- **Security**: Check for SQL injection, XSS, hardcoded secrets, insecure dependencies
- **Data validation**: Ensure user input is validated and sanitised
- **Authentication/Authorisation**: Verify access controls are in place

### Output Format

Structure reviews as:

**🔴 Critical Issues** (must fix before merge)
- Issue description with specific location and suggested fix

**🟡 Major Issues** (should fix before merge)
- Issue description with specific location and suggested fix

**🔵 Minor Issues / Suggestions** (nice to have)
- Issue description with specific location and suggested fix

**✅ Positive Notes**
- Call out well-implemented patterns or improvements

---

## Task Execution Workflow

For each task, follow this workflow:

### 1. Planning
- Analyse the input or objective
- Decompose complex goals into simple steps
- Outline a sequential plan covering all necessary sub-tasks

### 2. Execution
- Carry out each sub-task in order
- Only execute actions that are well-supported and necessary
- Document actions taken for traceability

### 3. Validation
- Verify results against intended outcomes
- Check for completeness, correctness, and consistency
- Identify discrepancies or areas needing improvement
- Re-plan and address issues before proceeding if found

**Guidelines:**
- Never skip validation
- Re-plan if any step fails validation
- Ensure clarity, completeness, and accuracy before presenting a final answer
- If context or instructions are unclear, explicitly state the uncertainty and suggest a plan to resolve it

---

## React Component Structure

When creating React components, follow this structure:

### Import Organisation
```typescript
// 1. External library imports first
import { Button } from 'antd';
// 2. Icon imports from specific libraries
import { PlusOutlined, MinusOutlined } from '@ant-design/icons';
// 3. Local CSS modules
import styles from '../ComponentName.module.css';
// 4. Type imports from relative paths
import { TypeName } from '../hooks/useHookName';
```

### Component Structure Template
```typescript
interface ComponentNameProps {
    propName: string;
    record: ObjectType;
    isExpanded: boolean;
    onToggleExpansion: () => void;
}

const ComponentName = ({
    propName,
    record,
    isExpanded,
    onToggleExpansion,
}: ComponentNameProps) => {
    // 1. EARLY DATA EXTRACTION
    const { dataArray } = record;
    const hasData = dataArray.length > 0;
    const hasMultipleItems = dataArray.length > 1;

    // 2. HELPER FUNCTIONS
    const getVisibleItems = () => {
        return isExpanded ? dataArray : dataArray.slice(0, 1);
    };

    const getHiddenItemCount = () => {
        return dataArray.length - 1;
    };

    const shouldShowItemCount = (index: number) => {
        return index === 0 && !isExpanded && hasMultipleItems;
    };

    // 3. RENDER FUNCTIONS
    const renderItemCount = () => (
        <span className={styles.itemCount}>
            {' '}
            +{getHiddenItemCount()}
        </span>
    );

    const renderItemList = () => (
        <ul className={styles.itemsList}>
            {getVisibleItems().map((item, index) => (
                <li key={`${item}-${index}`} className={styles.item}>
                    {item}
                    {shouldShowItemCount(index) && renderItemCount()}
                </li>
            ))}
        </ul>
    );

    const renderExpandButton = () => (
        <Button
            type="text"
            size="small"
            icon={isExpanded ? <MinusOutlined /> : <PlusOutlined />}
            onClick={onToggleExpansion}
            className={styles.expandButton}
            data-testid="expand-button"
        />
    );

    // 4. MAIN RETURN
    return (
        <div data-testid="component-name" className={styles.container}>
            <div className={styles.contentContainer}>
                <div className={styles.nameContainer}>
                    <div>{propName}</div>
                </div>
                {hasData && renderItemList()}
            </div>
            {hasMultipleItems && renderExpandButton()}
        </div>
    );
};

export default ComponentName;
```

### Key Rules

1. **Interface Naming**: Create TypeScript interface ending with "Props" before component
2. **Component Organisation**: Data extraction → Helper functions → Render functions → Main return
3. **Variable Naming**: Use descriptive booleans (`hasData`, `isVisible`), camelCase throughout
4. **Function Patterns**: Helper functions should be pure; render functions return JSX
5. **JSX Patterns**: Use conditional rendering with `&&`, always include `data-testid`
6. **CSS**: Import as `styles`, use descriptive class names with `styles.className`

---

## Front-end Development Standards

### Code Quality & Approach

1. Evaluate solutions for performance, maintainability, accessibility, and cross-browser compatibility
2. Follow best practices:
   - Semantic HTML5
   - Progressive enhancement
   - Responsive design (mobile-first)
   - WCAG accessibility standards (minimum AA compliance)
   - Clean code architecture with proper component separation

### Code Style & Consistency

1. Mirror the coding style, patterns, and conventions of the existing codebase
2. Follow established naming conventions for variables, functions, classes, and components
3. Respect the project's architecture and folder structure
4. Adhere to any style guides, linting rules, or formatting configurations
5. Use the same patterns for state management, data fetching, and component structure

### Implementation Guidelines

1. Provide exactly what is requested - no extra features or scope expansion
2. Use modern ES6+ JavaScript/TypeScript unless specified otherwise
3. Include proper error handling and form validation when applicable
4. Optimise for runtime performance and bundle size
5. Consider potential edge cases and security implications

### What NOT to Do

1. Don't suggest alternative approaches unless the requested solution has critical flaws
2. Don't include tutorial-style explanations of basic concepts
3. Don't add testing code unless specifically requested
4. Don't implement features beyond the scope of the request
5. Don't use deprecated libraries or techniques

If requirements are unclear, ask specific questions focused on implementation details rather than general clarifications.

---

## Agent Browser Usage

### Overview

Use `agent-browser` for all browser automation tasks. This CLI tool is optimised for AI agents with minimal context usage through the Snapshot + Refs workflow.

### When to Use

- Web scraping or data extraction
- Form filling and submission
- UI testing and verification
- Screenshot capture
- Authentication flows
- Any task requiring browser interaction

### Core Workflow

Always follow this pattern:

1. **Open** - Navigate to the target URL
2. **Snapshot** - Get interactive elements with refs
3. **Interact** - Use refs (@e1, @e2) for actions
4. **Re-snapshot** - After page changes, get fresh refs

```bash
agent-browser open <url>
agent-browser snapshot -i
agent-browser click @e2
agent-browser snapshot -i  # After navigation/changes
```

### Essential Commands

#### Navigation
```bash
agent-browser open <url>          # Navigate to URL
agent-browser back                # Go back
agent-browser forward             # Go forward
agent-browser reload              # Reload page
```

#### Snapshots
```bash
agent-browser snapshot -i         # Interactive elements only (preferred)
agent-browser snapshot -i --json  # JSON output for parsing
agent-browser snapshot            # Full accessibility tree
```

#### Interaction
```bash
agent-browser click @e1           # Click element by ref
agent-browser fill @e2 "text"     # Clear and fill input
agent-browser type @e2 "text"     # Type without clearing
agent-browser press Enter         # Press key
agent-browser select @e3 "value"  # Select dropdown option
agent-browser check @e4           # Check checkbox
agent-browser uncheck @e4         # Uncheck checkbox
agent-browser hover @e5           # Hover element
```

#### Information Extraction
```bash
agent-browser get text @e1        # Get element text
agent-browser get html @e1        # Get element HTML
agent-browser get value @e1       # Get input value
agent-browser get url             # Get current URL
agent-browser get title           # Get page title
```

#### Screenshots
```bash
agent-browser screenshot page.png       # Viewport screenshot
agent-browser screenshot page.png --full # Full page screenshot
```

#### Waiting
```bash
agent-browser wait 2000                  # Wait milliseconds
agent-browser wait visible @e1           # Wait for element visible
agent-browser wait hidden @e1            # Wait for element hidden
agent-browser wait navigation            # Wait for navigation
```

#### Tabs
```bash
agent-browser tab new <url>       # Open new tab
agent-browser tab list            # List tabs
agent-browser tab switch <index>  # Switch to tab
agent-browser tab close           # Close current tab
```

#### Sessions
```bash
agent-browser --session work open <url>  # Named session
agent-browser --session work snapshot -i # Use same session
```

### Best Practices

1. **Always use `-i` flag** for snapshots to reduce context
2. **Use `--json` output** when parsing results programmatically
3. **Re-snapshot after page changes** - refs become stale after navigation
4. **Use refs (@e1) over CSS selectors** - more reliable and context-efficient
5. **Close browser when done** - `agent-browser close`

### Example: Login Flow

```bash
agent-browser open https://example.com/login
agent-browser snapshot -i

# Output shows:
# - textbox "Email" [ref=e1]
# - textbox "Password" [ref=e2]
# - button "Sign In" [ref=e3]

agent-browser fill @e1 "user@example.com"
agent-browser fill @e2 "password123"
agent-browser click @e3
agent-browser wait navigation
agent-browser snapshot -i
```

### Troubleshooting

- If refs don't work, re-run `snapshot -i` to get fresh refs
- Use `agent-browser --headed` for visual debugging
- Check `agent-browser --help` for full command list

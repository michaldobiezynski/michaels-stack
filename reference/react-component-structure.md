# React Component Structure Template

Moved out of the global CLAUDE.md (2026-07-03) — read on demand when a project has no established component convention. Note: this template assumes Ant Design + CSS modules; always defer to the project's actual UI library and patterns.

## Import Organisation
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

## Component Structure Template
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

## Key Rules

1. **Interface Naming**: Create TypeScript interface ending with "Props" before component
2. **Component Organisation**: Data extraction → Helper functions → Render functions → Main return
3. **Variable Naming**: Use descriptive booleans (`hasData`, `isVisible`), camelCase throughout
4. **Function Patterns**: Helper functions should be pure; render functions return JSX
5. **JSX Patterns**: Use conditional rendering with `&&`, always include `data-testid`
6. **CSS**: Import as `styles`, use descriptive class names with `styles.className`

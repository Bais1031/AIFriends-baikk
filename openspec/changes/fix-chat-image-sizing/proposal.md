## Why

After implementing the image sending feature in the chat box, we've discovered that uploaded images sometimes exceed the chat container boundaries, causing layout issues and poor user experience. This affects the visual consistency of the chat interface and can break the responsive design on different screen sizes.

## What Changes

- Implement responsive image sizing that respects chat container boundaries
- Add max-width and max-height constraints to uploaded images in chat messages
- Ensure images maintain aspect ratio while fitting within the chat area
- Add proper CSS classes for different message types (user vs AI)
- Optimize image display for both light and dark themes

## Capabilities

### New Capabilities
- responsive-image-display: Implement proper image sizing constraints within the chat container
- chat-message-styling: Enhance message styling to properly handle image content

### Modified Capabilities
- (No existing capabilities require modification at the spec level)

## Impact

- Frontend Vue components in `frontend/src/components/`
- CSS styles in `frontend/src/assets/css/` or component-scoped styles
- Message rendering logic in chat components
- Responsive design across different screen sizes
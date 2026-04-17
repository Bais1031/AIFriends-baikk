## Context

The chat image feature has been implemented, but images uploaded by users are not properly constrained within the chat container. This leads to:
- Images overflowing the chat boundaries on smaller screens
- Layout issues when images have large dimensions
- Inconsistent appearance across different message types (user vs AI)
- Poor responsive behavior on mobile devices

Current implementation likely uses unrestricted image display without proper constraints.

## Goals / Non-Goals

**Goals:**
- Implement responsive image sizing that maintains aspect ratio
- Ensure all images fit within chat container boundaries
- Support different screen sizes (mobile, tablet, desktop)
- Maintain visual consistency for both user and AI messages
- Preserve image quality while constraining dimensions

**Non-Goals:**
- Image optimization/compression (already handled by backend)
- Implementing image galleries or carousels
- Adding zoom functionality for images
- Changing the image upload flow

## Decisions

### 1. CSS-based Image Constraint Approach
We'll use CSS `max-width: 100%` and `max-height: 300px` with `object-fit: contain` to ensure images fit within boundaries while maintaining aspect ratio.

**Rationale:** This is the simplest and most performant solution that works across all browsers and doesn't require JavaScript image processing.

### 2. Component-scoped Styling
Rather than global styles, we'll add image-specific CSS classes to the chat message components.

**Rationale:** Prevents style conflicts and makes the styling more maintainable within the component context.

### 3. Distinct Styling for User vs AI Messages
User messages will have left-aligned images with padding-right, while AI messages will have right-aligned images with padding-left.

**Rationale:** Maintains the visual distinction between message types while ensuring proper image display.

## Risks / Trade-offs

**[Risk] Large aspect ratio images** → Mitigation: Set reasonable max-height while maintaining object-fit: contain to avoid distortion

**[Risk] Image appears too small on desktop** → Mitigation: Use relative units and media queries to adjust max-height based on screen size

**[Trade-off] Performance** → CSS constraints are lightweight and don't impact performance compared to JavaScript-based solutions

**[Trade-off] Implementation complexity** → Using component-scoped CSS adds slight overhead but improves maintainability

## Migration Plan

1. Identify all components that render chat messages with images
2. Add CSS classes for image styling
3. Test across different screen sizes and image dimensions
4. Verify no regressions in existing message display

## Open Questions

- Should we add a fallback for very large images (>10MB)?
- Do we need different constraints for mobile vs desktop?
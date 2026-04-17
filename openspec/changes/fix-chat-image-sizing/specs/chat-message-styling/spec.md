## ADDED Requirements

### Requirement: Distinct styling for user and AI message images
Images in chat messages SHALL have different styling based on whether they are from the user or AI.

#### Scenario: User message image styling
- **WHEN** an image is displayed in a user message
- **THEN** the image is left-aligned
- **AND** padding-right: 12px is applied to separate from message text
- **AND** the image has a subtle border matching the user message bubble

#### Scenario: AI message image styling
- **WHEN** an image is displayed in an AI message
- **THEN** the image is right-aligned
- **AND** padding-left: 12px is applied to separate from message text
- **AND** the image has a subtle border matching the AI message bubble

### Requirement: Theme-aware image styling
Image styling SHALL adapt to light and dark themes.

#### Scenario: Light theme image display
- **WHEN** the chat is in light theme mode
- **THEN** images have a light background when needed
- **AND** image borders use light theme colors

#### Scenario: Dark theme image display
- **WHEN** the chat is in dark theme mode
- **THEN** images have a dark background when needed
- **AND** image borders use dark theme colors

### Requirement: Consistent image spacing
Images SHALL have consistent spacing within chat messages regardless of size.

#### Scenario: Image spacing with text
- **WHEN** an image is displayed with accompanying text
- **THEN** 8px vertical spacing is maintained between image and text
- **AND** horizontal spacing matches the message alignment

#### Scenario: Multiple images in a message
- **WHEN** multiple images are sent in a single message
- **THEN** each image is separated by 16px margin
- **AND** images stack vertically with proper spacing

### Requirement: Image loading behavior
Images SHALL load smoothly without disrupting the chat interface.

#### Scenario: Image loading state
- **WHEN** an image is loading
- **THEN** a loading placeholder is displayed
- **AND** the chat remains responsive during image loading

#### Scenario: Image load failure
- **WHEN** an image fails to load
- **THEN** a broken image icon is displayed
- **AND** the error is logged for debugging
import type { Preview } from '@storybook/react-vite';
import '../src/styles.css';
import '../src/stories/storybook.css';

const preview: Preview = {
  parameters: {
    a11y: {
      test: 'todo',
    },
    backgrounds: {
      default: 'Trapo Light',
      values: [
        { name: 'Trapo Light', value: '#ffffff' },
        { name: 'Workbench Panel', value: '#fafafd' },
      ],
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    layout: 'fullscreen',
  },
};

export default preview;

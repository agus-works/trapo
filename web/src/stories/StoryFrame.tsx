import type { ReactNode } from 'react';

export function StoryFrame({
  title,
  description,
  width = 'wide',
  children,
}: {
  title: string;
  description: string;
  width?: 'narrow' | 'standard' | 'wide';
  children: ReactNode;
}) {
  return (
    <main className="storybookCanvas">
      <div className="storybookFrame" data-width={width}>
        <header className="storybookTitle">
          <h1>{title}</h1>
          <p>{description}</p>
        </header>
        {children}
      </div>
    </main>
  );
}

import type { PointerEvent, RefObject } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';

export function usePreviewPan(scrollRef: RefObject<HTMLDivElement | null>) {
  const dragRef = useRef<{ pointerId: number; x: number; y: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [spacePressed, setSpacePressed] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code === 'Space' && !isEditableElement(document.activeElement)) {
        setSpacePressed(true);
      }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code === 'Space') {
        setSpacePressed(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, []);

  const onPointerDown = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (event.button !== 1 && !(spacePressed && event.button === 0)) {
        return;
      }
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
      setDragging(true);
    },
    [spacePressed],
  );

  const onPointerMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      const drag = dragRef.current;
      const scrollElement = scrollRef.current;
      if (!drag || drag.pointerId !== event.pointerId || !scrollElement) {
        return;
      }
      const deltaX = event.clientX - drag.x;
      const deltaY = event.clientY - drag.y;
      scrollElement.scrollLeft -= deltaX;
      scrollElement.scrollTop -= deltaY;
      dragRef.current = { ...drag, x: event.clientX, y: event.clientY };
    },
    [scrollRef],
  );

  const onPointerUp = useCallback((event: PointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
      setDragging(false);
    }
  }, []);

  return { dragging, onPointerDown, onPointerMove, onPointerUp, spacePressed };
}

function isEditableElement(element: Element | null): boolean {
  return (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement ||
    element?.getAttribute('contenteditable') === 'true'
  );
}

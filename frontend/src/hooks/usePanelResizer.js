import { useState, useRef, useEffect, useCallback } from 'react';
import { clamp } from '../utils/mathUtils';

const MIN_LEFT = 0;
const MIN_CENTER = 1;

export const usePanelResizer = (initialLeft = 50) => {
    const [sizes, setSizes] = useState({
        left: initialLeft,
    });
    const containerRef = useRef(null);
    const dragStateRef = useRef(null);

    useEffect(() => {
        const handlePointerMove = (event) => {
            if (!dragStateRef.current) {
                return;
            }

            event.preventDefault();

            const { type, startX, startLeft, containerWidth } = dragStateRef.current;

            if (type === 'left') {
                if (!containerWidth) {
                    return;
                }

                const deltaPercent = ((event.clientX - startX) / containerWidth) * 100;

                setSizes((prev) => {
                    const maxLeft = 100 - MIN_CENTER;
                    const safeMax = Math.max(MIN_LEFT, maxLeft);
                    const nextLeft = clamp(startLeft + deltaPercent, MIN_LEFT, safeMax);
                    const centerWidthPercent = 100 - nextLeft;

                    if (centerWidthPercent < MIN_CENTER) {
                        const adjustedLeft = 100 - MIN_CENTER;
                        return { ...prev, left: clamp(adjustedLeft, MIN_LEFT, safeMax) };
                    }

                    return { ...prev, left: nextLeft };
                });

                return;
            }
        };

        const stopDragging = () => {
            if (!dragStateRef.current) {
                return;
            }

            dragStateRef.current = null;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.body.classList.remove('is-resizing', 'is-resizing--vertical', 'is-resizing--horizontal');
        };

        window.addEventListener('mousemove', handlePointerMove);
        window.addEventListener('mouseup', stopDragging);

        return () => {
            window.removeEventListener('mousemove', handlePointerMove);
            window.removeEventListener('mouseup', stopDragging);
        };
    }, []);

    const beginDrag = useCallback((type) => (event) => {
        event.preventDefault();

        const containerRect = containerRef.current?.getBoundingClientRect();

        dragStateRef.current = {
            type,
            startX: event.clientX,
            startLeft: sizes.left,
            containerWidth: containerRect ? containerRect.width : 0,
        };

        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';
        document.body.classList.add('is-resizing', 'is-resizing--vertical');
    }, [sizes.left]);

    return {
        sizes,
        containerRef,
        beginDrag
    };
};

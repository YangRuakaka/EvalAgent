import { useEffect, useState } from 'react';

const getRect = (element) => {
	if (!element) {
		return { width: 0, height: 0, top: 0, left: 0 };
	}

	const rect = element.getBoundingClientRect();
	return {
		width: rect.width,
		height: rect.height,
		top: rect.top,
		left: rect.left,
	};
};

const defaultSize = Object.freeze({ width: 0, height: 0, top: 0, left: 0 });

const useResizeObserver = (ref) => {
	const [size, setSize] = useState(defaultSize);

	useEffect(() => {
		const node = ref.current;

		if (!node) {
			setSize(defaultSize);
			return undefined;
		}

		let frame;

		const notify = () => {
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(() => {
				setSize(getRect(node));
			});
		};

		const observer = new ResizeObserver(() => {
			notify();
		});

		notify();
		observer.observe(node);

		return () => {
			cancelAnimationFrame(frame);
			observer.disconnect();
		};
	}, [ref]);

	return size;
};

export default useResizeObserver;

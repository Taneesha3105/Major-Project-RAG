import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";

function ScrollJumpControls({ visible }) {
  const [canScroll, setCanScroll] = useState(false);
  const [isNearTop, setIsNearTop] = useState(true);
  const [isNearBottom, setIsNearBottom] = useState(true);

  useEffect(() => {
    if (!visible) {
      setCanScroll(false);
      setIsNearTop(true);
      setIsNearBottom(true);
      return undefined;
    }

    function updateScrollState() {
      const scrollTop = window.scrollY || window.pageYOffset || 0;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
      const scrollHeight = Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight,
      );

      setCanScroll(scrollHeight > viewportHeight + 120);
      setIsNearTop(scrollTop < 96);
      setIsNearBottom(scrollHeight - scrollTop - viewportHeight < 120);
    }

    updateScrollState();
    window.addEventListener("scroll", updateScrollState, { passive: true });
    window.addEventListener("resize", updateScrollState);

    return () => {
      window.removeEventListener("scroll", updateScrollState);
      window.removeEventListener("resize", updateScrollState);
    };
  }, [visible]);

  if (!visible || !canScroll) {
    return null;
  }

  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function scrollToLatest() {
    const scrollHeight = Math.max(
      document.documentElement.scrollHeight,
      document.body.scrollHeight,
    );

    window.scrollTo({ top: scrollHeight, behavior: "smooth" });
  }

  return (
    <div className="app-scroll-controls">
      <button
        type="button"
        className="icon-button app-scroll-button"
        onClick={scrollToTop}
        disabled={isNearTop}
        aria-label="Scroll to top"
        title="Scroll to top"
      >
        <ArrowUp size={18} />
      </button>
      <button
        type="button"
        className="icon-button app-scroll-button"
        onClick={scrollToLatest}
        disabled={isNearBottom}
        aria-label="Scroll to latest message"
        title="Scroll to latest message"
      >
        <ArrowDown size={18} />
      </button>
    </div>
  );
}

export default ScrollJumpControls;

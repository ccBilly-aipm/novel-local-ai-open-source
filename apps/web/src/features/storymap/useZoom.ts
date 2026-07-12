import { useEffect, useRef } from "react";
import { select } from "d3-selection";
import { zoom, zoomIdentity, ZoomBehavior } from "d3-zoom";

// 把 d3-zoom 行为挂到 <svg> 上，transform 应用到内部 <g ref=gRef>。
// 参考页 E1：scaleExtent 可配，双击复位（禁用 d3 默认双击放大）。
export function useZoom(
  svgRef: React.RefObject<SVGSVGElement>,
  gRef: React.RefObject<SVGGElement>,
  scaleExtent: [number, number] = [0.5, 8],
  deps: unknown[] = [],
): { reset: () => void } {
  const behaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  useEffect(() => {
    const svg = svgRef.current;
    const g = gRef.current;
    if (!svg || !g) return;
    const gSel = select(g);
    const z = zoom<SVGSVGElement, unknown>()
      .scaleExtent(scaleExtent)
      .on("zoom", (event) => {
        gSel.attr("transform", event.transform.toString());
      });
    behaviorRef.current = z;
    const svgSel = select(svg);
    svgSel.call(z).on("dblclick.zoom", null); // 禁用双击放大
    // 双击复位到 identity（不引入 d3-transition，直接 set；CSS 过渡由 <g> 承担平滑感）。
    svgSel.on("dblclick", () => {
      svgSel.call(z.transform, zoomIdentity);
    });
    return () => {
      svgSel.on(".zoom", null).on("dblclick", null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const reset = () => {
    const svg = svgRef.current;
    if (!svg || !behaviorRef.current) return;
    select(svg).call(behaviorRef.current.transform, zoomIdentity);
  };

  return { reset };
}

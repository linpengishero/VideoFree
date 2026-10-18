"""Plugin-owned grid splitting executor."""
import io
from PIL import Image
from backend.integrations.native import NativeExecutionCancelled, NativeExecutionContext, NativeExecutionResult

def execute_image_split(context: NativeExecutionContext) -> NativeExecutionResult:
    if len(context.references) != 1:
        raise ValueError("宫格分割需要且只能使用一张图片")
    if context.cancelled():
        raise NativeExecutionCancelled()
    body, _ = context.media_loader(context.references[0])
    try:
        with Image.open(io.BytesIO(body)) as source:
            image = source.convert("RGB")
            width, height = image.size
            if width < 2 or height < 2:
                raise ValueError("图片尺寸太小，无法分割")
            columns, rows = (3, 2) if context.config.get("grid") == "3x2" else (2, 2)
            x_edges = [round(width * index / columns) for index in range(columns + 1)]
            y_edges = [round(height * index / rows) for index in range(rows + 1)]
            boxes = tuple((x_edges[column], y_edges[row], x_edges[column + 1], y_edges[row + 1]) for row in range(rows) for column in range(columns))
            paths = []
            for index, box in enumerate(boxes, 1):
                if context.cancelled():
                    raise NativeExecutionCancelled()
                path = context.output_dir / f"{context.job_id}_{index}.png"
                image.crop(box).save(path, "PNG")
                paths.append(path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"无法读取待分割图片: {exc}") from exc
    cell_width = max((x_edges[index + 1] - x_edges[index] for index in range(columns)), default=width)
    cell_height = max((y_edges[index + 1] - y_edges[index] for index in range(rows)), default=height)
    return NativeExecutionResult(paths, cell_width, cell_height)

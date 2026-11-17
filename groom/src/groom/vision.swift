// groom's macOS helper, built from source by groom/src/groom/ocr.py with the system swiftc.
//
//   groom-vision ocr IMAGE          print the text in IMAGE as JSON (macOS Vision framework):
//                                   [{"text", "x", "y", "w", "h", "confidence"}], where x, y is
//                                   the centre and w, h the size, as fractions of the image,
//                                   with y measured from the top
//   groom-vision render SPEC OUT    draw a Kong-style 4x4 pad grid described by SPEC (JSON:
//                                   {"size": px, "pads": [{"pad", "label", "group"?}]}) to the
//                                   PNG file OUT; used for test fixtures

import AppKit
import Foundation
import Vision

struct Failure: Error, CustomStringConvertible {
    let description: String
}

func ocr(_ path: String) throws -> [[String: Any]] {
    guard let image = NSImage(contentsOfFile: path),
        let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
    else { throw Failure(description: "cannot read image \(path)") }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]  // Kong labels are Latin; avoids e.g. Cyrillic "М"
    request.automaticallyDetectsLanguage = false
    request.minimumTextHeight = 0.008
    try VNImageRequestHandler(cgImage: cg).perform([request])
    return (request.results ?? []).compactMap { observation in
        guard let best = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox  // normalised, origin at the bottom left
        return [
            "text": best.string, "x": box.midX, "y": 1 - box.midY, "w": box.width,
            "h": box.height, "confidence": best.confidence,
        ]
    }
}

struct PadSpec: Decodable {
    let pad: Int
    let label: String
    let group: Int?
}

struct GridSpec: Decodable {
    let size: Int
    let pads: [PadSpec]
}

func draw(_ text: String, at point: NSPoint, size: CGFloat, bold: Bool = false) {
    let font = bold ? NSFont.boldSystemFont(ofSize: size) : NSFont.systemFont(ofSize: size)
    NSAttributedString(
        string: text, attributes: [.font: font, .foregroundColor: NSColor.white]
    ).draw(at: point)
}

func render(_ specPath: String, _ out: String) throws {
    let spec = try JSONDecoder().decode(
        GridSpec.self, from: Data(contentsOf: URL(fileURLWithPath: specPath)))
    let size = spec.size
    guard
        let bitmap = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8,
            samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
            bytesPerRow: 0, bitsPerPixel: 0)
    else { throw Failure(description: "cannot make a bitmap") }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    NSColor(white: 0.12, alpha: 1).setFill()
    NSRect(x: 0, y: 0, width: size, height: size).fill()

    let cell = CGFloat(size) / 4
    for pad in spec.pads {
        // pad 1 is bottom left; AppKit's origin is bottom left too
        let col = CGFloat((pad.pad - 1) % 4)
        let row = CGFloat((pad.pad - 1) / 4)
        let rect = NSRect(x: col * cell, y: row * cell, width: cell, height: cell)
            .insetBy(dx: cell * 0.04, dy: cell * 0.04)
        NSColor(white: 0.3, alpha: 1).setFill()
        NSBezierPath(roundedRect: rect, xRadius: cell * 0.05, yRadius: cell * 0.05).fill()
        if let group = pad.group {
            draw(String(group), at: NSPoint(x: rect.minX + cell * 0.06, y: rect.maxY - cell * 0.2),
                size: cell * 0.11)
        }
        draw(pad.label, at: NSPoint(x: rect.minX + cell * 0.1, y: rect.minY + cell * 0.38),
            size: cell * 0.12, bold: true)
        draw(String(pad.pad), at: NSPoint(x: rect.maxX - cell * 0.2, y: rect.minY + cell * 0.38),
            size: cell * 0.1)
    }
    NSGraphicsContext.restoreGraphicsState()
    guard let png = bitmap.representation(using: .png, properties: [:])
    else { throw Failure(description: "cannot encode PNG") }
    try png.write(to: URL(fileURLWithPath: out))
}

let args = CommandLine.arguments
do {
    switch (args.count, args.count > 1 ? args[1] : "") {
    case (3, "ocr"):
        let json = try JSONSerialization.data(withJSONObject: try ocr(args[2]))
        FileHandle.standardOutput.write(json)
    case (4, "render"):
        try render(args[2], args[3])
    default:
        throw Failure(description: "usage: groom-vision ocr IMAGE | render SPEC OUT")
    }
} catch {
    FileHandle.standardError.write("groom-vision: \(error)\n".data(using: .utf8)!)
    exit(1)
}

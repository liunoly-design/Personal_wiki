// Apple Vision: https://developer.apple.com/documentation/vision/recognizing-text-in-images
import Foundation
import Vision
import ImageIO

do {
    guard CommandLine.arguments.count == 2 else { throw NSError(domain: "WikiOCR", code: 1) }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
        throw NSError(domain: "WikiOCR", code: 2)
    }
    let frameCount = CGImageSourceGetCount(source)
    guard frameCount > 0 && frameCount <= 500 else { throw NSError(domain: "WikiOCR", code: 3) }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false
    var frames: [[String: Any]] = []
    var uniqueLines: [[String: Any]] = []
    var seen = Set<String>()
    for frame in 0..<frameCount {
      try autoreleasepool {
       guard let image = CGImageSourceCreateImageAtIndex(source, frame, nil) else { throw NSError(domain: "WikiOCR", code: 4) }
       let properties = CGImageSourceCopyPropertiesAtIndex(source, frame, nil) as? [CFString: Any]
       let orientation = CGImagePropertyOrientation(rawValue: (properties?[kCGImagePropertyOrientation] as? UInt32) ?? 1) ?? .up
       try VNImageRequestHandler(cgImage: image, orientation: orientation).perform([request])
       let lines: [[String: Any]] = (request.results ?? []).compactMap { observation in
        guard let result = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return ["text": result.string, "confidence": result.confidence,
                "box": [box.origin.x, box.origin.y, box.width, box.height]]
       }
       frames.append(["frame": frame, "lines": lines])
       for line in lines {
        if let text = line["text"] as? String, seen.insert(text).inserted {
         var identified = line; identified["first_frame"] = frame; uniqueLines.append(identified)
        }
       }
      }
    }
    let data = try JSONSerialization.data(withJSONObject: ["engine": "Apple Vision", "revision": request.revision,
        "machine_generated": true, "frame_count": frameCount, "processed_frames": frames.count, "frames": frames, "lines": uniqueLines], options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
} catch {
    FileHandle.standardError.write(Data("Image text recognition failed; preserve original image.\n".utf8))
    exit(1)
}

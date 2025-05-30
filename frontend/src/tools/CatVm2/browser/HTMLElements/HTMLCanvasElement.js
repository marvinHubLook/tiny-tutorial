var HTMLCanvasElement = function HTMLCanvasElement() {
    throw new TypeError("Illegal constructor");
}
catvm.safefunction(HTMLCanvasElement);
Object.defineProperties(HTMLCanvasElement.prototype, {
    [Symbol.toStringTag]: {
        value: "HTMLCanvasElement",
        configurable: true
    }
});

catvm.memory.htmlelements["canvas"] = function () {
    var canvas = new (function () {
    });
    canvas.align = "";
    /////////////////////////
    canvas.__proto__ = HTMLCanvasElement.prototype;
    return canvas;
}

var CanvasRenderingContext2D = function CanvasRenderingContext2D() {
    throw new TypeError("Illegal constructor");
}
var WebGLRenderingContext = function WebGLRenderingContext() {
    throw new TypeError("Illegal constructor");
}

WebGLRenderingContext.prototype.RENDERER = 7937;
WebGLRenderingContext.prototype.VENDOR = 7936;
var parameters = {
    7936: "WebKit",
    7937: 'WebKit WebGL',
}

var _getParameter = function getParameter(parameter) {
    if (parameters[parameter]) {
        return parameters[parameter];
    } else {
        debugger;
        throw new Error("Unknown parameter: " + parameter);
    }
};
catvm.safefunction(_getParameter);
WebGLRenderingContext.prototype.getParameter = _getParameter;


catvm.safefunction(CanvasRenderingContext2D);
catvm.safefunction(WebGLRenderingContext);

//  getContext
HTMLCanvasElement.prototype.getContext = function getContext(contextId, contextAttributes) {
    // 这里可以添加一些逻辑来处理不同的contextId
    if (contextId === "2d") {
        return new CanvasRenderingContext2D();
    } else if (contextId === "webgl" || contextId === "experimental-webgl") {
        var _tmp = {}
        _tmp.__proto__ = WebGLRenderingContext.prototype;
        return _tmp;
    } else {
        throw new Error("Unsupported context type: " + contextId);
    }
};





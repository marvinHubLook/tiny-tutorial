var HTMLHtmlElement = function HTMLHtmlElement() { // 构造函数
    throw new TypeError("Illegal constructor");
};
catvm.safefunction(HTMLHtmlElement);

Object.defineProperties(HTMLHtmlElement.prototype, {
    [Symbol.toStringTag]: {
        value: "HTMLHtmlElement",
        configurable: true
    }
});
////////// 浏览器代码自动生成部分

////////
HTMLHtmlElement.prototype.getAttributeNames = function getAttributeNames() {
    // 返回一个空数组
    return ['lang'];
}

// 用户创建div
catvm.memory.htmlelements["html"] = function () {
    var html = new (function () {});
    html.__proto__ = HTMLHtmlElement.prototype;
    return html;
}


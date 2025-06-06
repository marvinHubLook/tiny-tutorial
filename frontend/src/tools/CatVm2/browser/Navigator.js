var Navigator = function Navigator() { // 构造函数
    throw new TypeError("Illegal constructor");
};
catvm.safefunction(Navigator);

Object.defineProperties(Navigator.prototype, {
    [Symbol.toStringTag]: {
        value: "Navigator",
        configurable: true
    }
});
navigator = {
    // platform: 'Win32',
    // userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36',
    // maxTouchPoints: 0,
    // onLine: true,
    // mimeTypes: [{
    //     suffixes: "pdf",
    //     type: "application/pdf"
    // }],
    //
    // plugins: [{
    //     "0": {},
    //     "1": {}
    // }]

};
navigator.__proto__ = Navigator.prototype;
////////// 浏览器代码自动生成部分

Navigator.prototype.plugins = [];
Navigator.prototype.vendor = 'Google Inc.';
Navigator.prototype.appVersion = '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36';
Navigator.prototype.languages = ["zh-CN", "zh"];
Navigator.prototype.userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36';
Navigator.prototype.platform = 'Win32';
Navigator.prototype.maxTouchPoints = 0;
Navigator.prototype.onLine = true;
Navigator.prototype.mimeTypes = [{
    suffixes: "pdf",
    type: "application/pdf"
}];
Navigator.prototype.plugins = [{
    "0": {},
    "1": {}
}];

var NetworkInformation = function NetworkInformation() { }
NetworkInformation.prototype = Object.create(Navigator.prototype, {
    [Symbol.toStringTag]: {
        value: "NetworkInformation",
        configurable: true
    }
});
var _networkInformation = {}
_networkInformation.__proto__ = NetworkInformation.prototype;

Navigator.prototype.connection = _networkInformation;
Navigator.prototype.productSub = '20030107'; // 这个是浏览器的版本号，Chrome是20030107
Navigator.prototype.webdriver = false; // 这个是浏览器是否被webdriver控制，Chrome是false
Navigator.prototype.language = "zh-CN"; // 这个是浏览器的语言，Chrome是zh-CN

var Permissions = function Permissions() { // 构造函数
    throw new TypeError("Illegal constructor");
};
catvm.safefunction(Permissions);
Object.defineProperties(Permissions.prototype, {
    [Symbol.toStringTag]: {
        value: "Permissions",
        configurable: true
    }
});
var _permissions = {};
_permissions.__proto__ = Permissions.prototype;
Navigator.prototype.permissions = _permissions;

//上面是定义原型的属性
// navigator比较特殊，它会把属性继续定义到 静态属性中，所以我们也做一下
for (var _prototype in Navigator.prototype) {
    navigator[_prototype] = Navigator.prototype[_prototype]; // 将原型上的方法复制一遍给实例
    if (typeof (Navigator.prototype[_prototype]) != "function") {
        // 相当于Object.defineProperty的get方法，Proxy的get方法，hook原型上的所有方法属性
        Navigator.prototype.__defineGetter__(_prototype, function () {
            debugger;
            var e = new Error();
            e.name = "TypeError";
            e.message = "Illegal constructor";
            e.stack = "VM988:1 Uncaught TypeError: Illegal invocation \r\n " +
                "at <anonymous>:1:21";
            throw e;
            // throw new TypeError("Illegal constructor");
        });
    }
}
////////


navigator = catvm.proxy(navigator);


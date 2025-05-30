var Location = function Location() { // 构造函数
    throw new TypeError("Illegal constructor");
};
catvm.safefunction(Location);

Object.defineProperties(Location.prototype, {
    [Symbol.toStringTag]: {
        value: "Location",
        configurable: true
    }
});
location = {};
location.__proto__ = Location.prototype;

////////// 浏览器代码自动生成部分
location.href = "https://ping0.cc";
location.port = "";
location.protocol = 'https:';
location.host = 'ping0.cc';
////////


location = catvm.proxy(location);
window.location = location


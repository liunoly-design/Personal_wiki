# nashsu 编译函数

来源：[nashsu/llm_wiki](https://github.com/nashsu/llm_wiki/tree/e8082119649e6a8e1cf85eaf289adcabfdf39d4e)，v0.6.11。原始文件：src/lib/ingest.ts、output-language.ts、wiki-page-types.ts。保留 GPL-3.0 许可证。

只提取分析提示词、生成提示词、FILE 解析器及纯依赖；显式固定中文输出，移除 UI/store 依赖。运行时不修改上游桌面程序。受控提交和状态恢复由本项目实现。
